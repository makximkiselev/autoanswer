import os
import asyncio
import logging
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from web.catalog_admin import router as catalog_admin_router
from web.source_api import router as source_router
from web.monitoring_api import router as monitoring_router
from web.unknowns_api import router as unknowns_router
from web.bindings import router as bindings_router
from web.matrix_api import router as matrix_router
from web.parsing_admin import router as parsing_admin_router
from web.catalog_public import router as catalog_public_router

from database import init_db, get_session
from config import API_TOKEN, client_configs
from utils import get_all_clients
from telethon_client import start_telethon_monitoring
from aiogram_bot import setup_aiogram_bot
from scheduler import start_scheduler
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

load_dotenv()
logging.getLogger("telethon").setLevel(logging.WARNING)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="web/templates")

monitoring_stats = {}  # Глобальный словарь для сбора статистики

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    with get_session() as session:
        session.execute(text("TRUNCATE TABLE processed_channels"))
        session.commit()
        logger.info("♻️ Таблица processed_channels очищена при старте FastAPI")

        session.execute(text("""
            ALTER TABLE IF EXISTS products
            ADD COLUMN IF NOT EXISTS approved BOOLEAN DEFAULT FALSE
        """))

        session.execute(text("""
            CREATE TABLE IF NOT EXISTS categories (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL
            );

            CREATE TABLE IF NOT EXISTS brands (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                category_id INTEGER REFERENCES categories(id)
            );

            CREATE TABLE IF NOT EXISTS models (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                brand_id INTEGER REFERENCES brands(id)
            );

            CREATE TABLE IF NOT EXISTS catalog_products (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                model_id INTEGER REFERENCES models(id),
                article TEXT
            );
        """))

        session.commit()

    start_scheduler()
    asyncio.create_task(setup_aiogram_bot())

    clients = await get_all_clients(client_configs)
    for client, label in clients:
        monitoring_stats[label] = {"channels": 0, "messages": 0, "products": 0}  # Инициализация
        asyncio.create_task(start_telethon_monitoring(client, label, monitoring_stats))

    yield

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Роутеры
app.include_router(catalog_admin_router)
app.include_router(monitoring_router)
app.include_router(source_router, prefix="/sources")
app.include_router(unknowns_router, prefix="/unknowns")
app.include_router(catalog_admin_router, prefix="/catalog")
app.include_router(bindings_router, prefix="/bindings")
app.include_router(matrix_router)
app.include_router(parsing_admin_router)
app.include_router(catalog_public_router)

app.mount("/static", StaticFiles(directory="web/static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/matrix", response_class=HTMLResponse)
async def matrix(request: Request):
    tree = {}
    return templates.TemplateResponse("matrix.html", {"request": request, "tree": tree})

@app.get("/monitoring/stats", response_class=HTMLResponse)
async def monitoring_stats_view(request: Request):
    return templates.TemplateResponse("monitoring_stats.html", {
        "request": request,
        "stats": monitoring_stats
    })

@app.get("/unknowns", response_class=HTMLResponse)
async def view_unknowns(request: Request):
    with get_session() as session:
        unknowns = session.execute(text("""
            SELECT * FROM unmatched_models ORDER BY first_seen DESC
        """)).fetchall()

        products = session.execute(text("""
            SELECT id, name FROM catalog_products ORDER BY name
        """)).fetchall()
        model_map = {row[0]: row[1] for row in products}

        categories = session.execute(text("SELECT id, name FROM categories ORDER BY name")).fetchall()
        brands = session.execute(text("SELECT DISTINCT name FROM brands ORDER BY name")).fetchall()
        models = session.execute(text("SELECT DISTINCT name FROM models ORDER BY name")).fetchall()

    return templates.TemplateResponse("unknowns.html", {
        "request": request,
        "unknowns": unknowns,
        "model_map": model_map,
        "categories": categories,
        "brands": brands,
        "models": models
    })

if __name__ == "__main__":
    print("\U0001F4CB Список маршрутов:")
    for route in app.router.routes:
        print(f"➡️ {getattr(route, 'path', '')}")
    uvicorn.run(app, host="127.0.0.1", port=8000)
