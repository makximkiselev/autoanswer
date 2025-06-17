import asyncio
from telethon.sync import TelegramClient
from telethon.tl.types import PeerChannel
from config import API_ID_1, API_HASH_1, SESSION_NAME_1  # или нужные тебе данные

async def main():
    async with TelegramClient(SESSION_NAME_1, API_ID_1, API_HASH_1) as client:
        try:
            peer = PeerChannel(1593822662)
            entity = await client.get_entity(peer)
            print(f"\n✅ Найдено: {entity} — тип: {type(entity)}\n")
        except Exception as e:
            print(f"\n❌ Ошибка при получении: {e}\n")

asyncio.run(main())
