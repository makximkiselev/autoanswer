# telethon_client.py

import os
import asyncio
import logging
from datetime import datetime
from telethon import TelegramClient, events
from telethon.tl.types import PeerChannel, PeerChat
from utils import ensure_messages_table, log_message, get_all_clients
from database import insert_product_if_new, save_source_id, get_allowed_sources_by_id
from llm import generate_reply

logger = logging.getLogger(__name__)
processed_messages = set()
_clients_cache = []

CLIENT_ALLOWED_CHANNELS = {}
CLIENT_ALLOWED_CHATS = {}
_resolved_accounts = set()  # 🧠 запоминаем, чтобы не дублировать логи

async def resolve_entity_ids(client: TelegramClient, account_id: str):
    first_run = account_id not in _resolved_accounts
    if first_run:
        _resolved_accounts.add(account_id)

    channels = []
    chats = []

    for type_, target_list in [("channel", channels), ("chat", chats)]:
        source_ids = get_allowed_sources_by_id(type_, account_id)
        if first_run:
            logger.info(f"📥 Источники типа {type_} для {account_id}: {source_ids}")
        for entity_id in source_ids:
            try:
                peer = PeerChannel(entity_id) if type_ == "channel" else PeerChat(entity_id)
                entity = await client.get_entity(peer)

                if type_ == "channel" and not getattr(entity, "broadcast", False):
                    continue
                if type_ == "chat" and not getattr(entity, "megagroup", False):
                    continue

                target_list.append(entity.id)
                title_or_id = entity.username or getattr(entity, "title", None) or str(entity.id)
                save_source_id(entity.id, title_or_id, type_)
            except Exception as e:
                if first_run:
                    logger.warning(f"❌ Не удалось получить {type_} {entity_id} (аккаунт: {account_id}): {e}")

    CLIENT_ALLOWED_CHANNELS[account_id] = channels
    CLIENT_ALLOWED_CHATS[account_id] = chats
    if first_run:
        logger.info(f"🔎 Разрешённые каналы ({account_id}): {channels}")
        logger.info(f"🔎 Разрешённые чаты ({account_id}): {chats}")

async def periodic_refresh_sources(client: TelegramClient, account_id: str):
    while True:
        try:
            await resolve_entity_ids(client, account_id)
        except Exception as e:
            logger.warning(f"Ошибка при обновлении источников (аккаунт: {account_id}): {e}")
        await asyncio.sleep(60)

async def fetch_history_from_allowed_sources():
    for client, account_id in _clients_cache:
        for source_type in ["channel", "chat"]:
            source_ids = get_allowed_sources_by_id(source_type, account_id)
            logger.info(f"📦 История {source_type} для {account_id}: {source_ids}")
            for source_id in source_ids:
                try:
                    peer = PeerChannel(source_id)
                    entity = await client.get_entity(peer)

                    async for message in client.iter_messages(entity, limit=50):
                        if message.text:
                            from parser import parse_message_text
                            parse_message_text(message.text, {
                                "account_id": account_id,
                                "channel_id": entity.id,
                                "channel_name": getattr(entity, "title", "unknown"),
                                "message_id": message.id,
                                "date": message.date
                            })
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка при загрузке истории из {source_type} {source_id} ({account_id}): {e}")

async def start_telethon_monitoring(client: TelegramClient, account_id: str, monitoring_stats: dict):
    logger.info(f"📦 Запуск мониторинга аккаунта: {account_id}")
    me = await client.get_me()
    logger.info(f"🔐 Авторизован: {me.username or me.phone} (как {account_id})")

    await resolve_entity_ids(client, account_id)
    asyncio.create_task(periodic_refresh_sources(client, account_id))
    asyncio.create_task(fetch_history_from_allowed_sources())

    monitoring_stats[account_id] = {
        "channels": 0,
        "messages": 0,
        "products": 0,
        "details": []
    }

    @client.on(events.NewMessage())
    async def live_handler(event):
        try:
            chat = await event.get_chat()
            chat_id = chat.id
            msg = event.message.message
            msg_id = event.message.id

            if (chat_id, msg_id) in processed_messages:
                return
            processed_messages.add((chat_id, msg_id))

            allowed_channels = CLIENT_ALLOWED_CHANNELS.get(account_id, [])
            allowed_chats = CLIENT_ALLOWED_CHATS.get(account_id, [])

            if chat_id not in allowed_channels and chat_id not in allowed_chats:
                return

            from parser import parse_message_text
            parse_message_text(msg, {
                "account_id": account_id,
                "channel_id": chat_id,
                "channel_name": getattr(chat, "title", "unknown"),
                "message_id": msg_id,
                "date": event.message.date
            })

            sender = await event.get_sender()
            log_message(
                chat_id=chat_id,
                user_id=sender.id,
                username=sender.username or "",
                text_msg=msg.strip(),
                timestamp=datetime.utcnow().isoformat(),
                account_id=account_id
            )

            # Обновление общей статистики
            monitoring_stats[account_id]["messages"] += 1

            # Обновление подробной статистики по источнику
            title = getattr(chat, "title", str(chat_id))
            detail = next((d for d in monitoring_stats[account_id]["details"] if d["channel"] == title), None)
            if detail:
                detail["messages"] += 1
            else:
                monitoring_stats[account_id]["details"].append({
                    "channel": title,
                    "messages": 1,
                    "products": 0
                })

            if chat_id in CLIENT_ALLOWED_CHATS.get(account_id, []):
                try:
                    reply = generate_reply(chat_id, msg.strip())
                    await client.send_message(chat_id, reply, reply_to=msg_id)
                    logger.info(f"✅ Ответ отправлен от {account_id} в чат {chat_id}")
                except Exception as e:
                    logger.warning(f"❌ Ошибка при генерации/отправке ответа: {e}")

        except Exception as e:
            logger.error(f"⚠️ Ошибка при live-обработке сообщения (аккаунт: {account_id}): {e}")

    await client.run_until_disconnected()
