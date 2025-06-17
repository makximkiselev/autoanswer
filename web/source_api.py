from fastapi import APIRouter, Request, Form, HTTPException, Path
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Optional
from database import get_session
from sqlalchemy import text
import asyncio
import logging
from pathlib import Path as FilePath
from telethon import TelegramClient
from telethon.tl.types import Channel, Chat, User
from config import (
    API_ID_1, API_HASH_1, SESSION_NAME_1, ACCOUNT_LABEL_1,
    API_ID_2, API_HASH_2, SESSION_NAME_2, ACCOUNT_LABEL_2
)
from contextlib import suppress
from asyncio import TimeoutError
from shutil import copyfile

router = APIRouter()
logger = logging.getLogger(__name__)
telethon_session_lock = asyncio.Lock()
templates = Jinja2Templates(directory="web/templates")

class SourceIn(BaseModel):
    name: str
    type: str
    monitored: bool = True

class SourceOut(BaseModel):
    id: int
    name: str
    type: str
    monitored: bool

KEYWORDS_MESSAGES = ["куплю", "ищу", "предложите", "предлагаю", "в наличии", "кому"]

@router.get("/", response_class=HTMLResponse)
def list_sources(request: Request, status: str = ""):
    with get_session() as session:
        records = session.execute(text("SELECT id, name, type, monitored, channel_id FROM source_ids ORDER BY type, name"))
        sources = records.fetchall()
    return templates.TemplateResponse("sources.html", {
        "request": request,
        "sources": sources,
        "status": status
    })

from typing import Optional

@router.post("/form", response_class=HTMLResponse)
async def add_source_form(
    request: Request,
    name: str = Form(...),
    type: Optional[str] = Form(None),  # теперь необязательный параметр
    monitored: str = Form("on")
):
    logger.info(f"🗕️ Попытка добавить источник: name={name}, type={type}, monitored={monitored}")
    monitored_bool = monitored == "on"

    matches = await collect_matches_from_clients(name)
    if not matches:
        logger.warning("❌ Не найдено подходящих чатов или каналов")
        return RedirectResponse(url="/sources/?status=notfound", status_code=303)

    if len(matches) > 1:
        with get_session() as session:
            sources = session.execute(
                text("SELECT id, name, type, monitored, channel_id FROM source_ids ORDER BY type, name")
            ).fetchall()
        return templates.TemplateResponse("sources.html", {
            "request": request,
            "status": "match",
            "name": name,
            "monitored": monitored_bool,
            "matches": matches,
            "sources": sources
        })

    selected = matches[0]
    try:
        with get_session() as session:
            existing = session.execute(
                text("SELECT id FROM source_ids WHERE name = :name"),
                {"name": name}
            ).fetchone()
            if existing:
                logger.warning("⚠️ Источник уже существует")
                return RedirectResponse(url="/sources/?status=exists", status_code=303)

            entity_type = selected["type"]

            if entity_type == "channel":
                final_type = "channel"
            elif entity_type == "chat":
                client = TelegramClient("sessions/temp_check", API_ID_1, API_HASH_1)
                await client.start()
                messages = [msg async for msg in client.iter_messages(selected["id"], limit=10)]
                await client.disconnect()
                found_keyword = any(
                    any(kw in (m.text or "").lower() for kw in KEYWORDS_MESSAGES)
                    for m in messages if hasattr(m, "text")
                )
                final_type = "chat_messages" if found_keyword else "chat_prices"
            else:
                final_type = entity_type

            session.execute(text("""
                INSERT INTO source_ids (name, type, monitored, channel_id, account_id)
                VALUES (:name, :type, :monitored, :channel_id, :account_id)
            """), {
                "name": name,
                "type": final_type,
                "monitored": monitored_bool,
                "channel_id": selected["id"],
                "account_id": selected["account_id"]
            })
            session.commit()

            added = session.execute(
                text("SELECT id FROM source_ids WHERE name = :name ORDER BY id DESC LIMIT 1"),
                {"name": name}
            ).fetchone()
            if not added:
                logger.error("❌ Ошибка вставки источника")
                return RedirectResponse(url="/sources/?status=fail", status_code=303)

            logger.info(f"✅ Источник добавлен с id={added[0]}, channel_id={selected['id']}")
        return RedirectResponse(url="/sources/?status=ok", status_code=303)
    except Exception as e:
        logger.exception("🔥 Исключение при добавлении источника")
        return RedirectResponse(url="/sources/?status=error", status_code=303)

@router.post("/{source_id}/toggle")
def toggle_monitored(source_id: int = Path(...)):
    with get_session() as session:
        result = session.execute(text("SELECT monitored FROM source_ids WHERE id = :id"), {"id": source_id}).fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="Источник не найден")
        new_state = not result[0]
        session.execute(text("UPDATE source_ids SET monitored = :state WHERE id = :id"), {"state": new_state, "id": source_id})
        session.commit()
    return RedirectResponse(url="/sources/?status=ok", status_code=303)

@router.post("/delete/{source_id}")
def delete_source(source_id: int):
    with get_session() as session:
        session.execute(text("DELETE FROM source_ids WHERE id = :id"), {"id": source_id})
        session.commit()
    return RedirectResponse(url="/sources/?status=ok", status_code=303)

@router.get("/api", response_model=List[SourceOut])
def list_sources_api():
    with get_session() as session:
        result = session.execute(text("SELECT id, name, type, monitored FROM source_ids ORDER BY type, name"))
        return [SourceOut(id=rec[0], name=rec[1], type=rec[2], monitored=rec[3]) for rec in result.fetchall()]

@router.post("/add-if-not-exists")
def add_if_not_exists(source: SourceIn):
    logger.info(f"🔍 Проверка или добавление источника: {source}")
    with get_session() as session:
        existing = session.execute(text("SELECT id FROM source_ids WHERE name = :name"), {"name": source.name}).fetchone()
        if existing:
            logger.info(f"↪️ Источник уже существует: {existing[0]}")
            return {"ok": True, "exists": True, "id": existing[0]}
        session.execute(
            text("INSERT INTO source_ids (name, type, monitored) VALUES (:name, :type, :monitored)"),
            {"name": source.name, "type": source.type, "monitored": source.monitored}
        )
        session.commit()
        added = session.execute(text("SELECT id FROM source_ids WHERE name = :name ORDER BY id DESC LIMIT 1"), {"name": source.name}).fetchone()
        logger.info(f"✅ Источник добавлен с id={added[0]}")
        return {"ok": True, "exists": False, "id": added[0]}

@router.post("/confirm-source")
async def confirm_source(request: Request, name: str = Form(...), type: str = Form(...), channel_id: int = Form(...), account_id: str = Form(...), monitored: Optional[str] = Form("on")):
    monitored_bool = monitored == "on"
    try:
        with get_session() as session:
            existing = session.execute(text("SELECT id FROM source_ids WHERE name = :name"), {"name": name}).fetchone()
            if existing:
                return RedirectResponse(url="/sources/?status=exists", status_code=303)
            session.execute(text("""
                INSERT INTO source_ids (name, type, monitored, channel_id, account_id)
                VALUES (:name, :type, :monitored, :channel_id, :account_id)
            """), {
                "name": name,
                "type": type,
                "monitored": monitored_bool,
                "channel_id": channel_id,
                "account_id": account_id
            })
            session.commit()
    except Exception as e:
        logger.exception("🔥 Ошибка при подтверждении источника")
        return RedirectResponse(url="/sources/?status=error", status_code=303)

    return RedirectResponse(url="/sources/?status=ok", status_code=303)

@router.get("/debug/routes")
def debug_routes():
    return [{"path": route.path, "methods": list(route.methods)} for route in router.routes if hasattr(route, 'path')]

@router.post("/test")
def test_post():
    return {"ok": True}

async def search_dialogs(api_id, api_hash, session_name, account_label, title: str):
    from telethon.errors.rpcerrorlist import FloodWaitError
    from telethon.errors import RPCError

    SESSIONS_DIR = FilePath("sessions")
    SESSIONS_DIR.mkdir(exist_ok=True)

    original_session_path = SESSIONS_DIR / f"{session_name}.session"
    if not original_session_path.exists():
        logger.warning(f"⛔ Пропуск: основной session-файл не найден для {account_label} — {original_session_path}")
        return []

    import uuid
    temp_session_name = f"{session_name}_search_{uuid.uuid4().hex[:8]}"
    temp_session_path = SESSIONS_DIR / f"{temp_session_name}.session"

    try:
        copyfile(original_session_path, temp_session_path)
    except Exception as e:
        logger.exception(f"❌ Ошибка копирования session-файла для {account_label}: {e}")
        return []

    logger.info(f"🔍 [search_dialogs] account_label={account_label} session_path={temp_session_path}")

    matches = []
    client = TelegramClient(temp_session_path, api_id, api_hash)

    try:
        await asyncio.wait_for(client.connect(), timeout=15)
        if not await client.is_user_authorized():
            logger.warning(f"⛔ [{account_label}] Клиент не авторизован. Пропуск.")
            return []
    except asyncio.TimeoutError:
        logger.error(f"❌ [{account_label}] Таймаут при client.connect()")
        return []
    except Exception as e:
        logger.exception(f"❌ [{account_label}] Ошибка при подключении: {e}")
        return []

    logger.info(f"🔌 [{account_label}] Подключен клиент, ищем '{title}'...")
    count = 0
    found = 0
    title_clean = title.strip().lower()

    async for dialog in client.iter_dialogs(limit=300):
        count += 1
        if not dialog.name:
            continue
        name_clean = dialog.name.strip().lower()
        if name_clean != title_clean:
            continue

        entity = dialog.entity
        found += 1
        logger.info(f"✅ [{account_label}] Найдено: {dialog.name} (type: {type(entity).__name__}, id: {entity.id})")

        if isinstance(entity, User):
            logger.info(f"⛔ [{account_label}] Пропущен пользователь '{dialog.name}'")
            continue
        elif isinstance(entity, Channel):
            matches.append({
                "id": entity.id,
                "name": dialog.name,
                "type": "channel",
                "account_id": account_label
            })
        elif isinstance(entity, Chat):
            matches.append({
                "id": entity.id,
                "name": dialog.name,
                "type": "chat",
                "account_id": account_label
            })

        if count % 50 == 0:
            logger.info(f"[{account_label}] Проверено {count} диалогов...")

    logger.info(f"📊 [{account_label}] Всего просмотрено {count} диалогов, совпадений: {found}")

    return matches

async def collect_matches_from_clients(title: str):
    async with telethon_session_lock:
        all_matches = []
        for cfg in [
            (API_ID_1, API_HASH_1, SESSION_NAME_1, ACCOUNT_LABEL_1),
            (API_ID_2, API_HASH_2, SESSION_NAME_2, ACCOUNT_LABEL_2)
        ]:
            logger.info(f"🔄 Запуск поиска по аккаунту: {cfg[3]}")
            matches = await search_dialogs(*cfg, title)
            all_matches.extend(matches)
        logger.info(f"🧾 Общее количество совпадений по всем аккаунтам: {len(all_matches)}")
        return all_matches
