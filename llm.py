# llm.py — генерация ответов через локальный Ollama

import requests
from datetime import datetime, timedelta
from database import get_connection

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "mistral"  # или llama2, gemma, openhermes и др.

def build_chat_context(chat_id: int, limit: int = 10) -> str:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT username, text, timestamp
                FROM messages
                WHERE chat_id = %s
                  AND timestamp >= %s
                ORDER BY timestamp ASC
                LIMIT %s
            """, (chat_id, (datetime.utcnow() - timedelta(hours=12)), limit))

            rows = cursor.fetchall()

    history = ""
    for username, text, ts in rows:
        history += f"[{username or 'пользователь'}] {text}\n"
    return history

def query_llm(prompt: str) -> str:
    response = requests.post(OLLAMA_URL, json={
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False
    })
    if response.ok:
        return response.json().get("response", "[Нет ответа от модели]")
    return f"[Ошибка от модели: {response.status_code}]"

def generate_reply(chat_id: int, user_text: str) -> str:
    context = build_chat_context(chat_id)
    full_prompt = f"""
Ты — продавец электроники. Клиент пишет: "{user_text}".
Вот история чата:
{context}
Ответь вежливо, предложи лучший вариант из прайс-листа. Аргументируй цену, торгуйся, напиши как человек.
"""
    return query_llm(full_prompt)
