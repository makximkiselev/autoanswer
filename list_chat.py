from telethon.sync import TelegramClient
from telethon.sessions import StringSession

# Вставь данные аккаунта
api_id = 28055972
api_hash = "c9c5f1ab6dd0ecf4492d35749cfdd249"
session = "session_apple_optom2"

client = TelegramClient(session, api_id, api_hash)

with client:
    for dialog in client.iter_dialogs():
        print(f"{dialog.name} — ID: {dialog.id} — type: {type(dialog.entity).__name__}")
