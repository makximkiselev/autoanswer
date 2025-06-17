import re
import spacy
import logging
import asyncio
import emoji
import unicodedata
from datetime import datetime
from sqlalchemy.sql import text
from telethon.errors import ChannelPrivateError, FloodWaitError

from database import get_connection, get_allowed_sources, save_unmatched_model, add_processed_channel, was_channel_processed, get_region_map
from normalizer import normalize_model_name
from utils import get_all_clients, ensure_messages_table, log_monitoring_result
from config import client_configs
from telethon_client import get_all_clients as get_cached_clients

nlp = spacy.load('ru_core_news_sm')
logger = logging.getLogger(__name__)

monitoring_stats = {}
region_map = get_region_map()

def fetch_exclusion_phrases():
    session = get_connection()
    try:
        rows = session.execute(text("SELECT phrase FROM exclusion_phrases")).fetchall()
        return [row[0].lower() for row in rows]
    finally:
        session.close()

def extract_product_parts(model_text: str):
    def extract_flag_emoji(text):
        flags = re.findall(r'[\U0001F1E6-\U0001F1FF]{2}', text)
        return flags[0] if flags else None

    def remove_non_flag_emojis(text):
        return ''.join(
            ch for ch in text if not (
                ch in emoji.EMOJI_DATA and not re.match(r'[\U0001F1E6-\U0001F1FF]', ch)
            )
        )

    raw_text = remove_non_flag_emojis(model_text)
    region_flag = extract_flag_emoji(model_text)
    region = region_flag if region_flag else None

    text = re.sub(r'[\U0001F1E6-\U0001F1FF]{2}', '', raw_text)
    text = re.sub(r'[^\w\s\-+]', '', text).strip()

    parts = text.lower().split()

    known_lineups = {
        "iphone": "Apple",
        "ipad": "Apple",
        "macbook": "Apple",
        "airpods": "Apple",
        "watch": "Apple",
        "imac": "Apple",
        "pixel": "Google",
        "galaxy": "Samsung",
        "note": "Xiaomi",
        "redmi": "Redmi",
        "mi": "Xiaomi",
        "poco": "Poco",
        "realme": "Realme",
        "oneplus": "OnePlus",
        "nokia": "Nokia",
    }

    brand = None
    lineup = None
    model = None

    for part in parts:
        if part in known_lineups:
            lineup = part
            brand = known_lineups[part]
            break

    if not brand:
        brand = "Unknown"

    model_tokens = []
    for word in parts:
        if re.match(r'\d{2,4}', word):
            break
        if word.lower() in ['teal', 'blue', 'black', 'white', 'natural', 'gray', 'gold', 'pink', 'red']:
            break
        model_tokens.append(word)

    model = ' '.join(model_tokens).title()

    region_map = {
        '🇺🇸': 'us', '🇷🇺': 'ru', '🇪🇺': 'eu', '🇭🇰': 'hk',
        '🇨🇳': 'cn', '🇰🇿': 'kz', '🇮🇳': 'in', '🇹🇭': 'th',
        '🇦🇪': 'ae', '🇲🇾': 'my', '🇯🇵': 'jp', '🇰🇷': 'kr'
    }
    region = region_map.get(region_flag, None)

    return brand, lineup, model, region

def extract_products_with_flags_and_price(line):
    results = []
    price_match = re.search(r"(\d{5,7})(?!\d)", line)
    if not price_match:
        return []

    price = int(price_match.group(1))
    price_start = price_match.start()
    text = line[:price_start].strip()

    flags = re.findall(r"[\U0001F1E6-\U0001F1FF]{2}", text)
    name = re.sub(r"[\U0001F1E6-\U0001F1FF]{2}", "", text)
    name = re.sub(r"[/\\]+", "", name).strip("•-:")

    if not flags:
        results.append({"name": name.strip(), "price": price, "flag": None})
    else:
        for flag in flags:
            results.append({"name": name.strip(), "price": price, "flag": flag})

    return results

def insert_price_or_unknown(session, model_text: str, price: int, flag: str, source: dict) -> bool:
    brand, lineup, model, region = extract_product_parts(model_text)
    name_std = normalize_model_name(f"{brand} {lineup or ''} {model} {region or ''}")

    cleaned = session.execute(
        text("SELECT id FROM products_cleaned WHERE name_std = :name_std"),
        {"name_std": name_std}
    ).first()

    if not cleaned:
        # ❌ Не удалось привязать — сохраняем как неизвестную модель
        save_unmatched_model(
            raw_name=model_text,
            source_channel=source.get("channel_name"),
            price=price,
            brand=brand,
            model=model,
            region=region,
            is_auto=False
        )
        return False

    standard_id = cleaned[0]

    # Проверка — есть ли product с таким name и standard_id
    product = session.execute(
        text("SELECT id FROM products WHERE standard_id = :standard_id AND name = :name"),
        {"standard_id": standard_id, "name": model_text}
    ).first()

    if product:
        product_id = product[0]
    else:
        product_id = session.execute(
            text("""
                INSERT INTO products (name, standard_id, approved)
                VALUES (:name, :standard_id, TRUE)
                RETURNING id
            """),
            {"name": model_text, "standard_id": standard_id}
        ).scalar()

    # Проверка — есть ли уже такая цена по message_id
    existing_price = session.execute(
        text("""
            SELECT 1 FROM prices
            WHERE product_id = :product_id AND message_id = :message_id
        """),
        {
            "product_id": product_id,
            "message_id": source.get("message_id")
        }
    ).first()

    if existing_price:
        return False  # ❌ Такая цена уже была, повторно не добавляем

    # ✅ Добавляем новую цену
    session.execute(
        text("""
            INSERT INTO prices (product_id, price, country, source_account, channel_name, message_id, message_date)
            VALUES (:product_id, :price, :country, :source_account, :channel_name, :message_id, :message_date)
        """),
        {
            "product_id": product_id,
            "price": price,
            "country": flag,
            "source_account": source.get("account_id"),
            "channel_name": source.get("channel_name"),
            "message_id": source.get("message_id"),
            "message_date": source.get("date").isoformat()
        }
    )

    return True

def parse_message_text(message_text: str, source: dict):
    updated_products = 0
    channel_id = source.get("channel_id")
    account_id = source.get("account_id")

    session = get_connection()
    try:
        # Проверка: источник разрешён?
        result = session.execute(
            text("SELECT 1 FROM source_ids WHERE channel_id = :channel_id AND account_id = :account_id"),
            {"channel_id": channel_id, "account_id": account_id}
        ).first()
        if result is None:
            logger.info(f"⛔ Источник {channel_id} (аккаунт {account_id}) не разрешён")
            return 0

        # Проверка: уже обрабатывался этим аккаунтом?
        result = session.execute(
            text("""SELECT 1 FROM processed_channels WHERE channel_id = :channel_id AND account_id = :account_id"""),
            {"channel_id": channel_id, "account_id": account_id}
        ).first()
        if result:
            logger.info(f"🔁 Источник {channel_id} уже обработан аккаунтом {account_id}")
            return 0

        ensure_messages_table()
        lines = message_text.splitlines()

        for line in lines:
            line = line.strip()
            if not line:
                continue

            match = re.search(r"(?P<price>\d{5,7})(?:\s?(?P<flag>[\U0001F1E6-\U0001F1FF]{2}))?", line)
            if not match:
                logger.debug(f"📭 Не распознано в строке: {line}")
                continue

            price = int(match.group("price"))
            flag = match.group("flag") if match.group("flag") else None
            model_text = re.sub(r"\d{5,7}(\s?[\U0001F1E6-\U0001F1FF]{2})?", "", line).strip("•- ")

            success = insert_price_or_unknown(session, model_text, price, flag, source)
            if success:
                updated_products += 1
                logger.info(f"✅ Добавлено: '{model_text}' за {price}₽ [{flag or 'без флага'}] — {source['channel_name']}")
            else:
                logger.info(f"❌ Пропущено: '{model_text}' — не добавлено — {source['channel_name']}")

        session.commit()
    except Exception as e:
        logger.warning(f"🔥 Ошибка при парсинге сообщения из {source.get('channel_name')}: {e}")
        session.rollback()
    finally:
        session.close()

    return updated_products

async def parse_all_channels(manual: bool = False):
    from telethon_client import get_all_clients as get_cached_clients
    from config import client_configs
    from database import get_allowed_sources

    logger = logging.getLogger(__name__)
    clients = await get_cached_clients(client_configs)
    monitoring_stats = {}

    for client, label in clients:
        if manual:
            logger.info(f"🧪 Ручной запуск парсинга для аккаунта: {label}")
        else:
            logger.info(f"🤖 Автоматический запуск парсинга для аккаунта: {label}")
        logger.info(f"🔁 Обрабатывается аккаунт: {label}")

        sources = get_allowed_sources("channel", label)
        stats = await parse_all_channels_with_stats(client, sources, label, manual_trigger=True)
        monitoring_stats[label] = stats

        # ✅ Логируем результат в monitoring_log.json
        log_monitoring_result(
            channels=stats["channels"],
            price_changes=stats["products"],
            details=stats["details"]
        )

    return monitoring_stats


# async-обёртка для was_channel_processed
async def was_channel_processed_async(channel_id: int, account_id: str) -> bool:
    from database import was_channel_processed
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, was_channel_processed, channel_id, account_id)

# основная функция
async def parse_all_channels_with_stats(client, sources, account_label, manual_trigger=False):

    # Удалим дубли каналов по channel_id
    sources = list({s["channel_id"]: s for s in sources}.values())

    stats = {"channels": 0, "messages": 0, "products": 0, "details": []}

    for source in sources:
        channel_id = source["channel_id"]

        if await was_channel_processed_async(channel_id, account_label):
            logger.info(f"🔁 Источник {channel_id} уже обработан аккаунтом {account_label}")
            continue

        try:
            entity = await client.get_entity(channel_id)
        except Exception as e:
            logger.warning(f"⚠️ Ошибка при получении entity для {channel_id}: {e}")
            continue

        logger.info(f"📥 Обработка канала: {getattr(entity, 'title', 'unknown')} (id={channel_id})")
        stats["channels"] += 1

        count = 0
        updated_total = 0

        try:
            async for message in client.iter_messages(entity, limit=None):  # ✅ читаем всё
                if not message.text:
                    continue

                count += 1
                updated = parse_message_text(message.text, {
                    "account_id": account_label,
                    "channel_id": entity.id,
                    "channel_name": getattr(entity, "title", "unknown"),
                    "message_id": message.id,
                    "date": message.date
                })

                if updated:
                    logger.debug(f"✅ Добавлено товаров: {updated} из сообщения {message.id}")

                updated_total += updated
                stats["products"] += updated
        except Exception as e:
            logger.exception(f"🔥 Ошибка при чтении сообщений канала {channel_id}")
            continue

        stats["messages"] += count
        stats["details"].append({
            "channel_name": getattr(entity, "title", "unknown"),
            "channel_id": entity.id,
            "messages": count,
            "products": updated_total
        })

        # ❗️Не помечаем канал как обработанный, если он почти пустой
        if count < 2:
            logger.warning(f"⚠️ Канал {channel_id} прочитан только на {count} сообщение — НЕ помечаем как обработанный")
            continue

        # ✅ Всё ок — можно пометить как обработанный
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, add_processed_channel, channel_id, account_label)

    return stats

