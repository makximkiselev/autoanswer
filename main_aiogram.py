# main_aiogram.py
from aiogram_bot import setup_aiogram_bot
import asyncio

if __name__ == "__main__":
    try:
        asyncio.run(setup_aiogram_bot())
    except (KeyboardInterrupt, SystemExit):
        print("🚫 Aiogram бот остановлен")
