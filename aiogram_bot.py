from aiogram import Bot, Dispatcher, F, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import CommandStart
from aiogram.client.default import DefaultBotProperties
import asyncio
import json
import logging
from config import API_TOKEN
from parser import parse_message_text
from scheduler import test_ping

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FSM и хранилище
storage = MemoryStorage()
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=storage)

USER_ID_FILE = "user_id.json"

def save_user_id(user_id: int):
    with open(USER_ID_FILE, "w") as f:
        json.dump({"user_id": user_id}, f)

def load_user_id():
    try:
        with open(USER_ID_FILE, "r") as f:
            return json.load(f).get("user_id")
    except Exception:
        return None

@dp.message(CommandStart())
async def cmd_start(message: Message):
    save_user_id(message.from_user.id)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚙️ Управление источниками", callback_data="manage_sources")]
    ])
    await message.answer("Добро пожаловать! Выберите действие:", reply_markup=keyboard)

@dp.callback_query(F.data == "manage_sources")
async def handle_manage_sources(callback_query: CallbackQuery):
    await callback_query.message.answer("🌐 Перейдите в веб-интерфейс для управления источниками: http://localhost:8000/sources")
    await callback_query.answer()

@dp.message(F.forward_from_chat | F.forward_from)
async def handle_forwarded_message(message: Message):
    if not message.text:
        await message.answer("⚠️ Это сообщение не содержит текста.")
        return

    source = {
        "account_id": "user_forward",
        "channel_id": None,
        "channel_name": "Переслано вручную",
        "message_id": message.message_id,
        "date": message.date
    }

    parse_message_text(message.text, source)
    await message.answer("✅ Прайс обработан и сохранён.")

@dp.message(F.text == "/ping")
async def handle_ping(message: Message):
    await test_ping()

async def setup_aiogram_bot():
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.exception("Ошибка при запуске aiogram бота")
