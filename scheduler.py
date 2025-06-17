from apscheduler.schedulers.asyncio import AsyncIOScheduler
import asyncio
import logging
import json
from datetime import datetime
from pathlib import Path
from aiogram import Bot
from parser import parse_all_channels_with_stats, parse_all_channels
from config import API_TOKEN
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from utils import log_monitoring_result


logger = logging.getLogger(__name__)
router = APIRouter()
scheduler = AsyncIOScheduler()
bot = Bot(token=API_TOKEN)

TICK_INTERVAL_MINUTES = 60

MONITORING_STATUS_FILE = Path("monitoring_status.json")
MONITORING_LOG_FILE = Path("monitoring_log.json")
USER_ID_FILE = Path("user_id.json")
templates = Jinja2Templates(directory="web/templates")

periodic_task = None


def load_monitoring_status() -> bool:
    try:
        if MONITORING_STATUS_FILE.exists():
            return json.loads(MONITORING_STATUS_FILE.read_text(encoding="utf-8")).get("enabled", False)
    except Exception:
        pass
    return False


def save_monitoring_status(enabled: bool):
    try:
        MONITORING_STATUS_FILE.write_text(
            json.dumps({"enabled": enabled}, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception as e:
        logger.warning(f"⚠️ Ошибка при сохранении monitoring_status.json: {e}")


def load_user_id():
    try:
        return json.load(USER_ID_FILE.open(encoding="utf-8")).get("user_id")
    except Exception:
        return None


def toggle_monitoring_parsing(enabled: bool):
    global periodic_task
    save_monitoring_status(enabled)

    if enabled:
        logger.info("✅ Мониторинг включён")

        async def periodic():
            while load_monitoring_status():
                try:
                    logger.info("⏰ Запуск парсера по расписанию.")
                    stats = await parse_all_channels(manual=True)

                    for label, stat in stats.items():
                        total_channels = stat.get("channels", 0)
                        total_products = stat.get("products", 0)
                        details = stat.get("details", [])

                        log_monitoring_result(
                            channels=total_channels,
                            price_changes=total_products,
                            details=details
                        )

                        user_id = load_user_id()
                        if user_id:
                            await bot.send_message(
                                chat_id=user_id,
                                text=f"📊 {label}: {total_channels} каналов, {total_products} товаров"
                            )
                except Exception as e:
                    logger.exception("🔥 Ошибка в мониторинге")

                await asyncio.sleep(TICK_INTERVAL_MINUTES * 60)

        periodic_task = asyncio.create_task(periodic())
    else:
        logger.info("🛑 Мониторинг остановлен")
        if periodic_task:
            periodic_task.cancel()
            periodic_task = None

@router.get("/monitoring", response_class=HTMLResponse)
async def monitoring_page(request: Request):
    history = []
    if MONITORING_LOG_FILE.exists():
        try:
            history = json.loads(MONITORING_LOG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return templates.TemplateResponse("monitoring.html", {
        "request": request,
        "monitoring_enabled": load_monitoring_status(),
        "history": list(reversed(history[-10:]))
    })


@router.post("/monitoring/toggle")
async def toggle_monitoring_ajax():
    current = load_monitoring_status()
    new_status = not current
    save_monitoring_status(new_status)
    toggle_monitoring_parsing(new_status)
    return JSONResponse(content={"ok": True, "enabled": new_status})


@router.get("/monitoring/run-parser")
async def run_parser_manual():
    try:
        stats = await parse_all_channels_with_stats(manual_trigger=True)
        total_channels = stats.get("channels", 0)
        total_products = stats.get("products", 0)
        details = stats.get("details", [])

        log_monitoring_result(
            channels=total_channels,
            price_changes=total_products,
            details=details
        )
        return RedirectResponse("/monitoring", status_code=303)
    except Exception as e:
        logger.exception("Ошибка при ручном запуске парсинга")
        return RedirectResponse("/monitoring", status_code=303)


async def test_ping():
    user_id = load_user_id()
    if not user_id:
        logger.warning("⚠️ user_id не найден")
        return
    try:
        await bot.send_message(chat_id=user_id, text="✅ Бот на связи. Всё работает.")
    except Exception as e:
        logger.exception("Ошибка при тестовой отправке")


def start_scheduler():
    scheduler.start()
    if load_monitoring_status():
        toggle_monitoring_parsing(True)
