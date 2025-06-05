import re
import spacy
from database import get_connection
from normalizer import normalize_model_name

nlp = spacy.load('ru_core_news_sm')

def parse_message_text(text: str, source: dict):
    from utils import ensure_messages_table

    channel_id = source.get("channel_id")
    account_id = source.get("account_id")

    with get_connection() as conn:
        with conn.cursor() as cursor:
            # Проверка, разрешён ли канал к парсингу
            cursor.execute("SELECT 1 FROM source_ids WHERE id = %s", (channel_id,))
            if cursor.fetchone() is None:
                print(f"⛔ Пропущен канал с ID {channel_id}, не входит в список разрешённых")
                return


            # Проверка, не был ли уже обработан этот канал другим аккаунтом
            cursor.execute(
                "SELECT account_id FROM processed_channels WHERE channel_id = %s",
                (channel_id,)
            )
            row = cursor.fetchone()
            if row and row["account_id"] != account_id:
                print(f"🔁 Пропущен канал {channel_id}, уже обработан аккаунтом {row['account_id']}")
                return

            # Обновление или вставка текущего аккаунта
            cursor.execute(
                "INSERT INTO processed_channels (channel_id, account_id) VALUES (%s, %s) ON CONFLICT (channel_id) DO UPDATE SET account_id = EXCLUDED.account_id",
                (channel_id, account_id)
            )

            print(f"\n🔍 Парсим сообщение из {source['channel_name']} (аккаунт: {account_id})")
            ensure_messages_table()
            lines = text.splitlines()

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                match = re.search(r"(?P<price>\d{5,7})(?:\s?(?P<flag>[\U0001F1E6-\U0001F1FF]{1,2}))?", line)
                if not match:
                    continue

                price = int(match.group("price"))
                flag = match.group("flag") if match.group("flag") else None

                model_text = re.sub(r"\d{5,7}(\s?[\U0001F1E6-\U0001F1FF]{1,2})?", "", line).strip("\u2022- ")

                doc = nlp(model_text)
                brand, lineup, model, region = None, None, None, None

                for ent in doc.ents:
                    if ent.label_ == "ORG" and not brand:
                        brand = ent.text.strip()
                    elif ent.label_ == "PRODUCT" and not model:
                        model = ent.text.strip()

                known_lineups = ["iphone", "ipad", "macbook", "watch", "galaxy", "note", "pixel"]
                parts = model_text.lower().split()

                for part in parts:
                    if part in known_lineups:
                        lineup = part
                for part in parts[::-1]:
                    if part in ["ch", "us", "eu", "hk", "ae", "my", "jp", "kr"]:
                        region = part

                if not brand:
                    brand = parts[0].capitalize() if parts else "Unknown"
                if not model:
                    model = model_text

                name_std = f"{brand} {lineup or ''} {model} {region or ''}".strip().replace("  ", " ")

                cursor.execute("SELECT id FROM products_cleaned WHERE name_std = %s", (name_std,))
                cleaned = cursor.fetchone()

                if cleaned:
                    standard_id = cleaned["id"] if isinstance(cleaned, dict) and "id" in cleaned else cleaned[0]
                else:
                    if brand.lower() == "unknown" or len(model.split()) < 2:
                        cursor.execute(
                            "INSERT INTO unmatched_models (raw_name, source_channel, first_seen, sample_price) VALUES (%s, %s, %s, %s)",
                            (model_text, source["channel_name"], source["date"].isoformat(), price)
                        )
                        continue

                    cursor.execute(
                        "INSERT INTO products_cleaned (brand, lineup, model, region, name_std) VALUES (%s, %s, %s, %s, %s)",
                        (brand, lineup, model, region, name_std)
                    )
                    cursor.execute("SELECT currval(pg_get_serial_sequence('products_cleaned','id'))")
                    row = cursor.fetchone()
                    if row:
                        standard_id = row["id"] if isinstance(row, dict) and "id" in row else row[0]
                    else:
                        continue

                cursor.execute("SELECT id FROM products WHERE standard_id = %s AND name = %s", (standard_id, model_text))
                product = cursor.fetchone()

                if not product:
                    cursor.execute("INSERT INTO products (name, standard_id) VALUES (%s, %s)", (model_text, standard_id))
                    cursor.execute("SELECT currval(pg_get_serial_sequence('products','id'))")
                    product_id_row = cursor.fetchone()
                    if not product_id_row:
                        continue
                    product_id = product_id_row["id"] if isinstance(product_id_row, dict) and "id" in product_id_row else product_id_row[0]
                else:
                    product_id = product["id"] if isinstance(product, dict) and "id" in product else product[0]

                cursor.execute(
                    '''
                    INSERT INTO prices (product_id, price, country, source_account, channel_name, message_id, message_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ''',
                    (
                        product_id,
                        price,
                        flag,
                        account_id,
                        source["channel_name"],
                        source["message_id"],
                        source["date"].isoformat()
                    )
                )
        conn.commit()

def extract_price(text):
    match = re.search(r"\b(\d{4,7})\b", text.replace(" ", ""))
    return int(match.group(1)) if match else None

def extract_model_ner(text):
    doc = nlp(text)
    for ent in doc.ents:
        if ent.label_ in ['PRODUCT', 'ORG', 'WORK_OF_ART']:
            return ent.text.strip()

    match = re.search(r"(iPhone|Samsung|Xiaomi|Redmi|Pixel)\s?([\w\s\-+]+)", text, re.I)
    if match:
        return f"{match.group(1)} {match.group(2)}".strip()

    return None

def parse_price_message(message):
    model = extract_model_ner(message)
    price = extract_price(message)
    if not model or not price:
        return None
    return {
        "brand": model.split()[0],
        "model": model,
        "price": price
    }

async def parse_all_channels():
    from database import get_allowed_sources
    from telethon import TelegramClient
    from telethon_client import get_all_clients
    import os
    from main import client_configs  # или импортируй client_configs напрямую, если нужно

    clients = await get_all_clients(client_configs)

    for client, label in clients:
        sources = get_allowed_sources("channel")
        for name in sources:
            try:
                entity = await client.get_entity(name)
                async for message in client.iter_messages(entity, limit=50):
                    if message.text:
                        parse_message_text(message.text, {
                            "account_id": label,
                            "channel_id": entity.id,
                            "channel_name": getattr(entity, "title", "unknown"),
                            "message_id": message.id,
                            "date": message.date
                        })
            except Exception as e:
                print(f"Ошибка при парсинге {name}: {e}")
