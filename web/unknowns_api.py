from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from database import get_session
from normalizer import normalize_model_name
from typing import Optional
import asyncio

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")

@router.get("/", response_class=HTMLResponse)
async def view_unknowns(request: Request, page: int = 1):
    limit = 50
    offset = (page - 1) * limit

    with get_session() as session:
        total = session.execute(text("SELECT COUNT(*) FROM unmatched_models")).scalar()

        unknowns = session.execute(text("""
            SELECT id, raw_name, detected_region, region_flag FROM unmatched_models 
            ORDER BY first_seen DESC
            LIMIT :limit OFFSET :offset
        """), {"limit": limit, "offset": offset}).mappings().all()

        products = session.execute(text("""
            SELECT id, name FROM catalog_products ORDER BY name
        """)).fetchall()
        model_map = {row[0]: row[1] for row in products}

        categories = session.execute(text("SELECT id, name FROM categories ORDER BY name")).fetchall()
        brands = session.execute(text("SELECT name FROM brands ORDER BY name")).fetchall()
        models = session.execute(text("SELECT name FROM models ORDER BY name")).fetchall()
        regions = session.execute(text("SELECT code, name, flag FROM regions ORDER BY name")).fetchall()

    total_pages = max(1, (total + limit - 1) // limit)

    return templates.TemplateResponse("unknowns.html", {
        "request": request,
        "unknowns": unknowns,
        "model_map": model_map,
        "categories": categories,
        "brands": brands,
        "models": models,
        "regions": regions,
        "total_pages": total_pages,
        "current_page": page
    })


@router.post("/approve")
async def approve_unknown(
    request: Request,
    approved_ids: Optional[str] = Form(""),
    model_ids: Optional[str] = Form("")
):
    form_data = await request.form()
    approved = approved_ids.split(",") if approved_ids else []

    model_map = {}
    for part in model_ids.split(","):
        if ":" in part:
            uid, mid = part.split(":")
            model_map[int(uid)] = int(mid)

    with get_session() as session:
        for uid in approved:
            uid_int = int(uid)
            model_id = model_map.get(uid_int)

            # Получаем код региона из формы
            region_code = form_data.get(f"region_code_{uid}", "").strip().lower()

            # Добавим регион в таблицу regions, если его ещё нет
            if region_code:
                exists = session.execute(
                    text("SELECT 1 FROM regions WHERE code = :code"),
                    {"code": region_code}
                ).first()
                if not exists:
                    session.execute(
                        text("INSERT INTO regions (code, name) VALUES (:code, :name)"),
                        {"code": region_code, "name": region_code.upper()}
                    )

            # Обновляем запись
            session.execute(
                text("""
                    UPDATE unmatched_models
                    SET is_approved = true,
                        model_id = :mid,
                        detected_region = :region
                    WHERE id = :uid
                """),
                {"uid": uid_int, "mid": model_id, "region": region_code or None}
            )

        session.commit()

    return RedirectResponse("/unknowns", status_code=303)


@router.get("/api/catalog/search")
async def search_catalog_models(q: str):
    with get_session() as session:
        rows = session.execute(text("""
            SELECT id, name FROM catalog_products
            WHERE LOWER(name) LIKE :term
            ORDER BY name LIMIT 10
        """), {"term": f"%{q.lower()}%"}).fetchall()
        return [{"id": row.id, "name": row.name} for row in rows]

@router.post("/reset-processed")
async def reset_processed_channels():
    with get_session() as session:
        session.execute(text("TRUNCATE TABLE processed_channels"))
        session.commit()
    return {"status": "ok", "message": "processed_channels очищена"}

@router.post("/create-and-confirm")
def create_and_confirm_product(
    request: Request,
    unmatched_id: int = Form(...),
    category_id: int = Form(...),
    brand_name: str = Form(...),
    model_name: str = Form(...),
    product_name: str = Form(...),
    region_code: Optional[str] = Form(None)
):
    from normalizer import normalize_model_name
    from datetime import datetime

    try:
        with get_session() as session:
            # 1. Получаем строку из unmatched_models
            unmatched = session.execute(
                text("SELECT * FROM unmatched_models WHERE id = :id"),
                {"id": unmatched_id}
            ).fetchone()
            if not unmatched:
                raise HTTPException(status_code=404, detail="Строка не найдена")

            # 2. Получаем или создаём бренд
            brand = session.execute(
                text("SELECT id FROM brands WHERE name = :name AND category_id = :cat_id"),
                {"name": brand_name, "cat_id": category_id}
            ).first()
            brand_id = brand[0] if brand else session.execute(
                text("INSERT INTO brands (name, category_id) VALUES (:name, :cat_id) RETURNING id"),
                {"name": brand_name, "cat_id": category_id}
            ).scalar()

            # 3. Получаем или создаём модель
            model = session.execute(
                text("SELECT id FROM models WHERE name = :name AND brand_id = :brand_id"),
                {"name": model_name, "brand_id": brand_id}
            ).first()
            model_id = model[0] if model else session.execute(
                text("INSERT INTO models (name, brand_id) VALUES (:name, :brand_id) RETURNING id"),
                {"name": model_name, "brand_id": brand_id}
            ).scalar()

            # 4. Создаём catalog_product
            product_id = session.execute(
                text("INSERT INTO catalog_products (name, model_id) VALUES (:name, :model_id) RETURNING id"),
                {"name": product_name, "model_id": model_id}
            ).scalar()

            # 5. Добавляем регион
            region = region_code or unmatched.detected_region
            if region:
                exists = session.execute(
                    text("SELECT 1 FROM regions WHERE code = :code"),
                    {"code": region}
                ).first()
                if not exists:
                    session.execute(
                        text("INSERT INTO regions (code, name) VALUES (:code, :name)"),
                        {"code": region, "name": region.upper()}
                    )

            # 6. Строим name_std
            name_std = normalize_model_name(f"{brand_name} {model_name} {unmatched.detected_model or ''} {region or ''}")

            # 7. Добавляем в products_cleaned
            session.execute(
                text("""
                    INSERT INTO products_cleaned (brand, lineup, model, region, name_std, catalog_product_id)
                    VALUES (:brand, :lineup, :model, :region, :name_std, :catalog_id)
                """),
                {
                    "brand": brand_name,
                    "lineup": model_name,
                    "model": unmatched.detected_model or unmatched.raw_name,
                    "region": region,
                    "name_std": name_std,
                    "catalog_id": product_id
                }
            )

            # 8. Добавляем в products
            session.execute(
                text("""
                    INSERT INTO products (name, standard_id, approved)
                    VALUES (:name, (SELECT id FROM products_cleaned WHERE name_std = :name_std), TRUE)
                """),
                {"name": unmatched.raw_name, "name_std": name_std}
            )

            # 🔥 9. Добавляем в prices
            session.execute(
                text("""
                    INSERT INTO prices (product_id, price, updated_at)
                    VALUES (
                        (SELECT id FROM products WHERE name = :name AND standard_id = (SELECT id FROM products_cleaned WHERE name_std = :name_std)),
                        :price,
                        :now
                    )
                """),
                {
                    "name": unmatched.raw_name,
                    "name_std": name_std,
                    "price": unmatched.sample_price or 0,
                    "now": datetime.now().isoformat()
                }
            )

            # 10. Удаляем из unmatched_models
            session.execute(
                text("DELETE FROM unmatched_models WHERE id = :id"),
                {"id": unmatched_id}
            )

            session.commit()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при подтверждении: {e}")

    return RedirectResponse(url="/unknowns", status_code=303)


@router.post("/exclude")
def exclude_unmatched(request: Request, unmatched_id: int = Form(...)):
    try:
        with get_session() as session:
            # Получаем raw_text
            raw = session.execute(
                text("SELECT raw_text FROM unmatched_models WHERE id = :id"),
                {"id": unmatched_id}
            ).scalar()

            if not raw:
                raise HTTPException(status_code=404, detail="Не найдено")

            # Проверяем — нет ли уже такой фразы в исключениях
            exists = session.execute(
                text("SELECT 1 FROM exclusion_phrases WHERE phrase = :raw"),
                {"raw": raw}
            ).first()

            if not exists:
                session.execute(
                    text("INSERT INTO exclusion_phrases (phrase) VALUES (:raw)"),
                    {"raw": raw}
                )

            # Удаляем из unmatched_models
            session.execute(
                text("DELETE FROM unmatched_models WHERE id = :id"),
                {"id": unmatched_id}
            )

            session.commit()
            return RedirectResponse("/unknowns", status_code=303)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@router.post("/clear-unmatched")
async def clear_unmatched_models():
    print("🧹 Очищаю unmatched_models")  # Лог для проверки, вызывается ли функция

    with get_session() as session:
        session.execute(text("TRUNCATE TABLE unmatched_models RESTART IDENTITY CASCADE"))
        session.commit()

    return RedirectResponse(url="/unknowns", status_code=303)

@router.get("/api/rows", response_class=HTMLResponse)
async def load_unknowns_rows(request: Request, page: int = 1):
    limit = 50
    offset = (page - 1) * limit

    with get_session() as session:
        unknowns = session.execute(text("""
            SELECT 
                um.id,
                um.raw_name,
                um.detected_region,
                r.flag AS region_flag
            FROM unmatched_models um
            LEFT JOIN regions r ON r.code = um.detected_region
            ORDER BY um.first_seen DESC
            LIMIT :limit OFFSET :offset
        """), {"limit": limit, "offset": offset}).mappings().all()

        products = session.execute(text("SELECT id, name FROM catalog_products ORDER BY name")).fetchall()
        model_map = {row[0]: row[1] for row in products}

        regions = session.execute(text("SELECT code, name, flag FROM regions ORDER BY name")).fetchall()

    return templates.TemplateResponse("partials/unknowns_rows.html", {
        "request": request,
        "unknowns": unknowns,
        "model_map": model_map,
        "regions": regions
    })
