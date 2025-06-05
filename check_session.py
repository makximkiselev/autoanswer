from telethon import TelegramClient

# Заменить на нужные значения
SESSION_NAME = "sessions/session_el_opt"  # путь до .session
API_ID = 24689382
API_HASH = "de16c5259726045d3bf8bf46fc2c46ac"

async def main():
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    print("✅ Авторизован аккаунт:")
    print(f"Username: {me.username}")
    print(f"Phone: {me.phone}")
    await client.disconnect()

import asyncio
asyncio.run(main())
