import os
import asyncio
import logging
import uvicorn
from dotenv import load_dotenv
from telethon import TelegramClient
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
from telethon_client import start_telethon_monitoring
from aiogram_bot import setup_aiogram_bot
from web.source_api import router as source_router
from parser import parse_all_channels  # ← Функция сбора прайсов

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_TOKEN = os.getenv("API_TOKEN")

client_configs = [
    {
        "session": os.getenv("SESSION_NAME_1"),
        "api_id": int(os.getenv("API_ID_1")),
        "api_hash": os.getenv("API_HASH_1"),
        "label": "account_1"
    },
    {
        "session": os.getenv("SESSION_NAME_2"),
        "api_id": int(os.getenv("API_ID_2")),
        "api_hash": os.getenv("API_HASH_2"),
        "label": "account_2"
    }
]

clients = []
scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    SESSIONS_DIR = "sessions"
    for cfg in client_configs:
        session_path = os.path.join(SESSIONS_DIR, f"{cfg['session']}.session")
        client = TelegramClient(session_path, cfg["api_id"], cfg["api_hash"])
        await client.start()
        clients.append((client, cfg["label"]))
        logger.info(f"Клиент {cfg['label']} авторизован")

    # 🔁 Запуск фонового мониторинга сообщений
    asyncio.create_task(monitor_all_channels(clients))

    # ⏰ Планировщик запуска parse_all_channels раз в час
    scheduler.add_job(lambda: asyncio.create_task(parse_all_channels()), 'interval', minutes=60)
    scheduler.start()

    # 🤖 Aiogram-бот
    bot = Bot(token=API_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    setup_aiogram_bot(dp)
    asyncio.create_task(dp.start_polling(bot))

    yield

app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="web/templates")
app.include_router(source_router, prefix="/sources")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# 📥 Запуск парсинга по кнопке
@app.get("/run-parser", response_class=HTMLResponse)
async def run_parser(request: Request):
    asyncio.create_task(parse_all_channels())
    return templates.TemplateResponse("index.html", {"request": request, "message": "🔁 Парсинг запущен"})

@app.get("/matrix", response_class=HTMLResponse)
async def matrix(request: Request):
    tree = {}
    return templates.TemplateResponse("matrix.html", {"request": request, "tree": tree})

# 📡 Фоновый мониторинг чатов
async def monitor_all_channels(clients):
    for client, label in clients:
        try:
            await start_telethon_monitoring(client, label)
        except Exception as e:
            logger.exception(f"Ошибка при мониторинге ({label}): {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)