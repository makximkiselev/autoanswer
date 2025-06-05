from telethon import TelegramClient

API_ID = 28055972  # или нужный для второго аккаунта
API_HASH = "c9c5f1ab6dd0ecf4492d35749cfdd249"
SESSION_NAME = "sessions/session_el_opt"

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

async def main():
    await client.start()  # ← здесь он спросит номер телефона и код
    me = await client.get_me()
    print(f"✅ Вошли как: {me.username or me.phone}")
    await client.disconnect()

import asyncio
asyncio.run(main())
