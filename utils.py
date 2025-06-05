# utils.py

import re
from database import get_connection


def normalize_model_name(text):
    text = text.lower()
    text = re.sub(r"[^a-z0-9 ]", "", text)
    text = text.replace("gb", "")
    parts = text.strip().split()
    return " ".join(sorted(parts))


def get_unique_field_values(field: str) -> list:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"""
                SELECT DISTINCT {field}
                FROM products_cleaned
                WHERE {field} IS NOT NULL AND TRIM({field}) != ''
                ORDER BY {field} ASC
            """)
            rows = cursor.fetchall()
            return [r[0] for r in rows if r[0]]


def ensure_messages_table():
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
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
            ''')
            conn.commit()


def log_message(chat_id, user_id, username, text, timestamp, account_id, direction="incoming"):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                INSERT INTO messages (chat_id, user_id, username, text, timestamp, account_id, direction)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (chat_id, user_id, username, text, timestamp, account_id, direction))
            conn.commit()


def get_recent_dialogue(chat_id: int, limit=10) -> str:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                SELECT direction, username, text
                FROM messages
                WHERE chat_id = %s
                ORDER BY timestamp DESC
                LIMIT %s
            ''', (chat_id, limit))
            rows = cursor.fetchall()

    dialogue = ""
    for direction, username, text in reversed(rows):
        if direction == "incoming":
            dialogue += f"👤 {username or 'Пользователь'}: {text}\n"
        else:
            dialogue += f"🤖 Менеджер: {text}\n"
    return dialogue.strip()


def get_unapproved_responses():
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                SELECT id, chat_id, user_id, text, reply
                FROM messages
                WHERE approved IS NULL
                ORDER BY timestamp DESC
                LIMIT 100
            ''')
            return cursor.fetchall()


def approve_message(message_id: int, is_approved: bool):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                UPDATE messages
                SET approved = %s
                WHERE id = %s
            ''', (is_approved, message_id))
            conn.commit()
