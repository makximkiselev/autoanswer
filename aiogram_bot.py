# aiogram_bot.py

from aiogram import Router, F
from aiogram.types import Message
from parser import parse_message_text

router = Router()

def setup_aiogram_bot(dp):
    dp.include_router(router)

@router.message(F.forward_from_chat | F.forward_from)
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
