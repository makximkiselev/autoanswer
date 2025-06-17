from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import asyncio
import logging
import json
from pathlib import Path
from parser import parse_all_channels
from utils import log_monitoring_result, MONITORING_LOG_FILE
from config import client_configs
from telethon_client import get_all_clients
from database import get_allowed_sources

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")
logger = logging.getLogger(__name__)

MONITORING_STATUS_FILE = Path("monitoring_status.json")

def schedule_periodic_parsing(interval_minutes: int = 60):
    async def periodic():
        while True:
            try:
                if MONITORING_STATUS_FILE.exists():
                    with open(MONITORING_STATUS_FILE, "r", encoding="utf-8") as f:
                        status = json.load(f)
                        if not status.get("enabled", False):
                            logger.info("🔕 Мониторинг отключён, пропуск запуска")
                            await asyncio.sleep(interval_minutes * 60)
                            continue

                logger.info("⏰ Запуск мониторинга по расписанию...")
                stats = await parse_all_channels(manual=True)
                for label, result in stats.items():
                    log_monitoring_result(
                        channels=result.get("channels", 0),
                        price_changes=result.get("products", 0),
                        details=result.get("details", [])
                    )
            except Exception as e:
                logger.exception("🔥 Ошибка при периодическом мониторинге")
            await asyncio.sleep(interval_minutes * 60)

    asyncio.create_task(periodic())

@router.get("/monitoring/run-parser", response_class=HTMLResponse)
async def run_monitoring_ui(request: Request):
    stats = await parse_all_channels(manual=True)

    formatted_stats = {}
    detailed_stats = {}

    for label, result in stats.items():
        formatted_stats[label] = {
            "channels": result.get("channels", 0),
            "messages": result.get("messages", 0),
            "products": result.get("products", 0),
        }

        detailed_stats[label] = result.get("details", [])

    return templates.TemplateResponse("monitoring_stats.html", {
        "request": request,
        "stats": formatted_stats,
        "details": detailed_stats
    })

@router.post("/monitoring/run-parser")
async def run_monitoring():
    async def wrapper():
        logger.info("🧪 [POST] Ручной запуск parse_all_channels()")
        try:
            stats = await parse_all_channels(manual=True)
            for label, result in stats.items():
                log_monitoring_result(
                    channels=result.get("channels", 0),
                    price_changes=result.get("products", 0),
                    details=result.get("details", [])
                )
        except Exception as e:
            logger.exception("🔥 Ошибка при ручном запуске мониторинга")

    asyncio.create_task(wrapper())
    return {"ok": True, "message": "🔁 Парсинг запущен вручную"}


@router.post("/monitoring/toggle")
async def toggle_monitoring_ajax():
    monitoring_enabled = False
    if MONITORING_STATUS_FILE.exists():
        try:
            with open(MONITORING_STATUS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                monitoring_enabled = data.get("enabled", False)
        except Exception:
            pass

    new_status = not monitoring_enabled
    try:
        with open(MONITORING_STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump({"enabled": new_status}, f, ensure_ascii=False, indent=2)
    except Exception:
        return JSONResponse(content={"ok": False, "error": "write_failed"})

    return JSONResponse(content={"ok": True, "enabled": new_status})

@router.get("/monitoring", response_class=HTMLResponse)
async def monitoring_page(request: Request):
    monitoring_enabled = False
    history = []

    if MONITORING_STATUS_FILE.exists():
        try:
            with open(MONITORING_STATUS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                monitoring_enabled = data.get("enabled", False)
        except Exception:
            pass

    if MONITORING_LOG_FILE.exists():
        try:
            with open(MONITORING_LOG_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            pass

    return templates.TemplateResponse("monitoring.html", {
        "request": request,
        "monitoring_enabled": monitoring_enabled,
        "history": history[-20:][::-1],
    })
