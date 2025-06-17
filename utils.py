import os
import re
import asyncio
import json
import logging
from sqlalchemy import text
from database import get_connection
from telethon import TelegramClient
from datetime import datetime
from pathlib import Path


logger = logging.getLogger(__name__)
MONITORING_LOG_FILE = Path("monitoring_log.json")

_clients_cache = []
_clients_lock = asyncio.Lock()

def normalize_model_name(text):
    text = text.lower()
    text = re.sub(r"[^a-z0-9 ]", "", text)
    text = text.replace("gb", "")
    parts = text.strip().split()
    return " ".join(sorted(parts))

def get_unique_field_values(field: str) -> list:
    session = get_connection()
    try:
        result = session.execute(text(f"""
            SELECT DISTINCT {field}
            FROM products_cleaned
            WHERE {field} IS NOT NULL AND TRIM({field}) != ''
            ORDER BY {field} ASC
        """))
        return [row[0] for row in result.fetchall() if row[0]]
    finally:
        session.close()

def ensure_messages_table():
    session = get_connection()
    try:
        session.execute(text('''
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT,
                user_id BIGINT,
                username TEXT,
                text TEXT,
                timestamp TEXT,
                account_id TEXT,
                direction TEXT DEFAULT 'incoming',
                approved BOOLEAN DEFAULT NULL
            )
        '''))
        session.commit()
    finally:
        session.close()

def log_message(chat_id, user_id, username, text_msg, timestamp, account_id, direction="incoming"):
    session = get_connection()
    try:
        session.execute(text('''
            INSERT INTO messages (chat_id, user_id, username, text, timestamp, account_id, direction)
            VALUES (:chat_id, :user_id, :username, :text, :timestamp, :account_id, :direction)
        '''), {
            "chat_id": chat_id,
            "user_id": user_id,
            "username": username,
            "text": text_msg,
            "timestamp": timestamp,
            "account_id": account_id,
            "direction": direction
        })
        session.commit()
    finally:
        session.close()

def get_recent_dialogue(chat_id: int, limit=10) -> str:
    session = get_connection()
    try:
        result = session.execute(text('''
            SELECT direction, username, text
            FROM messages
            WHERE chat_id = :chat_id
            ORDER BY timestamp DESC
            LIMIT :limit
        '''), {"chat_id": chat_id, "limit": limit}).fetchall()
    finally:
        session.close()

    dialogue = ""
    for direction, username, text_msg in reversed(result):
        if direction == "incoming":
            dialogue += f"\U0001F464 {username or 'Пользователь'}: {text_msg}\n"
        else:
            dialogue += f"\U0001F916 Менеджер: {text_msg}\n"
    return dialogue.strip()

def get_unapproved_responses():
    session = get_connection()
    try:
        return session.execute(text('''
            SELECT id, chat_id, user_id, text, reply
            FROM messages
            WHERE approved IS NULL
            ORDER BY timestamp DESC
            LIMIT 100
        ''')).fetchall()
    finally:
        session.close()

def approve_message(message_id: int, is_approved: bool):
    session = get_connection()
    try:
        session.execute(text('''
            UPDATE messages
            SET approved = :approved
            WHERE id = :id
        '''), {"approved": is_approved, "id": message_id})
        session.commit()
    finally:
        session.close()

async def get_all_clients(client_configs):
    global _clients_cache
    if _clients_cache:
        return _clients_cache

    async with _clients_lock:
        if _clients_cache:
            return _clients_cache

        SESSIONS_DIR = "sessions"
        os.makedirs(SESSIONS_DIR, exist_ok=True)

        for cfg in client_configs:
            session_path = os.path.join(SESSIONS_DIR, f"{cfg['session']}.session")
            client = TelegramClient(session_path, cfg["api_id"], cfg["api_hash"])

            try:
                await client.connect()
                if not await client.is_user_authorized():
                    print(f"⚠️ Сессия {cfg['label']} не авторизована. Пропускаем.")
                    continue
                _clients_cache.append((client, cfg["label"]))
            except Exception as e:
                print(f"❌ Ошибка при запуске клиента {cfg['label']}: {e}")
                continue

    return _clients_cache

def generate_article(category: str, brand: str, model: str, product_id: int) -> str:
    cat = category[:3].upper()
    br = brand[:3].upper()
    mod = ''.join(model.split())[:3].upper()
    return f"{cat}-{br}-{mod}-{product_id:05d}"

def log_monitoring_result(channels=0, price_changes=0, details=None):
    try:
        if not MONITORING_LOG_FILE.exists():
            MONITORING_LOG_FILE.write_text("[]", encoding="utf-8")

        with open(MONITORING_LOG_FILE, "r", encoding="utf-8") as f:
            log = json.load(f)

        log.append({
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "channels_checked": channels,
            "price_changes": price_changes,
            "details": details or []
        })

        with open(MONITORING_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(log, f, indent=2, ensure_ascii=False)

    except Exception as e:
        logger.exception("🔥 Ошибка при сохранении monitoring_log.json")