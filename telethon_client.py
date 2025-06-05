from telethon import TelegramClient, events
from parser import parse_message_text
from utils import ensure_messages_table, log_message
from database import insert_product_if_new, save_source_id, get_allowed_sources
from datetime import datetime
from llm import generate_reply
from telethon import TelegramClient
import logging
import asyncio
import os


logger = logging.getLogger(__name__)
processed_messages = set()

_clients_cache = []

# Глобальные переменные (заполняются через БД)
ALLOWED_CHANNEL_IDS = []
ALLOWED_CHAT_IDS = []

async def resolve_entity_ids(client: TelegramClient):
    """
    Получаем ID всех разрешённых источников (channel/chat) из БД.
    Обновляем локальные списки и сохраняем entity ID в БД.
    """
    global ALLOWED_CHANNEL_IDS, ALLOWED_CHAT_IDS

    source_types = [("channel", ALLOWED_CHANNEL_IDS), ("chat", ALLOWED_CHAT_IDS)]

    for source_type, target_list in source_types:
        target_list.clear()
        sources = get_allowed_sources(source_type)
        for name_or_id in sources:
            try:
                entity = await client.get_entity(name_or_id)
                target_list.append(entity.id)
                save_source_id(entity.id, name_or_id, source_type)
            except Exception as e:
                logger.warning(f"Не удалось получить ID для {source_type} '{name_or_id}': {e}")

async def start_telethon_monitoring(client: TelegramClient, account_id: str):
    logger.info(f"📦 Запуск мониторинга аккаунта: {account_id}")
    me = await client.get_me()
    logger.info(f"🔐 Авторизован: {me.username or me.phone}")

    await resolve_entity_ids(client)

    # Исторический парсинг только из разрешённых каналов
    for channel_id in ALLOWED_CHANNEL_IDS:
        try:
            entity = await client.get_entity(channel_id)
            async for message in client.iter_messages(entity, limit=50):
                if message.text:
                    parse_message_text(message.text, {
                        "account_id": account_id,
                        "channel_id": entity.id,
                        "channel_name": getattr(entity, "title", "unknown"),
                        "message_id": message.id,
                        "date": message.date
                    })
        except Exception as e:
            logger.warning(f"❌ Ошибка доступа к каналу {channel_id}: {e}")

    # Обработка новых сообщений
    @client.on(events.NewMessage())
    async def live_handler(event):
        try:
            chat = await event.get_chat()
            if chat.id not in ALLOWED_CHANNEL_IDS and chat.id not in ALLOWED_CHAT_IDS:
                return

            msg = event.message.message
            msg_id = event.message.id

            if (chat.id, msg_id) in processed_messages:
                return
            processed_messages.add((chat.id, msg_id))

            # Парсинг и сохранение товара (если канал)
            if chat.id in ALLOWED_CHANNEL_IDS:
                parse_message_text(msg, {
                    "account_id": account_id,
                    "channel_id": chat.id,
                    "channel_name": getattr(chat, "title", "unknown"),
                    "message_id": msg_id,
                    "date": event.message.date
                })

            # Логирование всех сообщений
            sender = await event.get_sender()
            log_message(
                chat_id=chat.id,
                user_id=sender.id,
                username=sender.username or "",
                text=msg.strip(),
                timestamp=datetime.utcnow().isoformat(),
                account_id=account_id
            )

            # Генерация ответа (если чат)
            if chat.id in ALLOWED_CHAT_IDS:
                reply = generate_reply(chat.id, msg.strip())
                await client.send_message(chat.id, reply, reply_to=msg_id)
                logger.info(f"✅ Ответ отправлен от {account_id} в чат {chat.id}")

        except Exception as e:
            logger.error(f"⚠️ Ошибка при live-обработке сообщения: {e}")

    await client.run_until_disconnected()

async def get_all_clients(client_configs):
    """
    Загружает и возвращает все TelegramClient'ы согласно конфигу.
    Кэширует результат, чтобы не создавать сессии повторно.
    """
    global _clients_cache
    if _clients_cache:
        return _clients_cache

    SESSIONS_DIR = "sessions"
    for cfg in client_configs:
        session_path = os.path.join(SESSIONS_DIR, f"{cfg['session']}.session")
        client = TelegramClient(session_path, cfg["api_id"], cfg["api_hash"])
        await client.start()
        _clients_cache.append((client, cfg["label"]))
    return _clients_cache
