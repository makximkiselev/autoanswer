from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from typing import List
from database import get_connection
import asyncio
import logging

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SourceIn(BaseModel):
    name: str
    type: str
    monitored: bool = True

class SourceOut(BaseModel):
    id: int
    name: str
    type: str
    monitored: bool

@router.get("/", response_class=HTMLResponse)
def list_sources(request: Request, status: str = ""):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, name, type, monitored FROM source_ids ORDER BY type, name")
            rows = cursor.fetchall()
    return templates.TemplateResponse("sources.html", {"request": request, "sources": rows, "status": status})

@router.post("/form", response_class=RedirectResponse)
def add_source_form(request: Request, name: str = Form(...), type: str = Form(...), monitored: str = Form("on")):
    logger.info(f"🗕️ Попытка добавить источник: name={name}, type={type}, monitored={monitored}")
    monitored_bool = monitored == "on"
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id FROM source_ids WHERE name = %s", (name,))
                if cursor.fetchone():
                    logger.warning("⚠️ Источник уже существует")
                    return RedirectResponse(url="/sources/?status=exists", status_code=303)
                cursor.execute(
                    "INSERT INTO source_ids (name, type, monitored) VALUES (%s, %s, %s) RETURNING id",
                    (name, type, monitored_bool)
                )
                row = cursor.fetchone()
                if not row:
                    logger.error("❌ Ошибка вставки источника")
                    return RedirectResponse(url="/sources/?status=fail", status_code=303)
                conn.commit()
                logger.info(f"✅ Источник добавлен с id={row[0]}")
        return RedirectResponse(url="/sources/?status=ok", status_code=303)
    except Exception as e:
        logger.exception("🔥 Исключение при добавлении источника")
        return RedirectResponse(url="/sources/?status=error", status_code=303)

@router.post("/{source_id}/toggle")
def toggle_monitored(source_id: int):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT monitored FROM source_ids WHERE id = %s", (source_id,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Источник не найден")
            new_state = not row[0]
            cursor.execute("UPDATE source_ids SET monitored = %s WHERE id = %s", (new_state, source_id))
            conn.commit()
    return RedirectResponse(url="/sources/?status=ok", status_code=303)

@router.post("/{source_id}")
def delete_source(source_id: int, method: str = Form(..., alias="_method")):
    if method != "delete":
        raise HTTPException(status_code=405, detail="Метод не поддерживается")
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM source_ids WHERE id = %s", (source_id,))
            conn.commit()
    return RedirectResponse(url="/sources/?status=ok", status_code=303)

@router.get("/api", response_model=List[SourceOut])
def list_sources_api():
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, name, type, monitored FROM source_ids ORDER BY type, name")
            rows = cursor.fetchall()
    return [SourceOut(id=row[0], name=row[1], type=row[2], monitored=row[3]) for row in rows]

@router.post("/run-parser")
async def run_parser():
    from parser import parse_all_channels
    asyncio.create_task(parse_all_channels())
    return {"ok": True, "message": "Manual price collection started"}

@router.post("/add-if-not-exists")
def add_if_not_exists(source: SourceIn):
    logger.info(f"🔍 Проверка или добавление источника: {source}")
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM source_ids WHERE name = %s", (source.name,))
            row = cursor.fetchone()
            if row:
                logger.info(f"↪️ Источник уже существует: {row[0]}")
                return {"ok": True, "exists": True, "id": row[0]}
            cursor.execute(
                "INSERT INTO source_ids (name, type, monitored) VALUES (%s, %s, %s) RETURNING id",
                (source.name, source.type, source.monitored)
            )
            row = cursor.fetchone()
            conn.commit()
            logger.info(f"✅ Источник добавлен с id={row[0]}")
            return {"ok": True, "exists": False, "id": row[0]}

@router.get("/debug/routes")
def debug_routes():
    routes_info = []
    for route in router.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            routes_info.append({"path": route.path, "methods": list(route.methods)})
    return routes_info

@router.post("/test")
def test_post():
    return {"ok": True}
