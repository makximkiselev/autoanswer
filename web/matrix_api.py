from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from database import get_session
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")

@router.get("/matrix", response_class=HTMLResponse)
def view_matrix(request: Request):
    try:
        with get_session() as session:
            rows = session.execute(text("""
                SELECT
                    pc.id AS cleaned_id,
                    pc.catalog_product_id AS category,
                    pc.brand,
                    pc.lineup,
                    pc.model,
                    pc.name_std,
                    pc.region,
                    pr.price
                FROM products_cleaned pc
                LEFT JOIN products p ON pc.id = p.standard_id
                LEFT JOIN prices pr ON p.id = pr.product_id
                WHERE p.approved = true
                ORDER BY pc.catalog_product_id, pc.brand, pc.model, pc.region, pr.price
            """)).fetchall()

        tree = {}

        for row in rows:
            category = row.category or "❓Без категории"
            brand = row.brand or "❓Без бренда"
            model = row.model or row.name_std or "❓Без модели"
            region = row.region or "—"
            price = row.price
            cleaned_id = row.cleaned_id

            if category not in tree:
                tree[category] = {}
            if brand not in tree[category]:
                tree[category][brand] = {}
            if model not in tree[category][brand]:
                tree[category][brand][model] = {"_cleaned_id": cleaned_id}

            if region not in tree[category][brand][model]:
                tree[category][brand][model][region] = []

            if price is not None:
                tree[category][brand][model][region].append(price)

        result = {}
        for category, brands in tree.items():
            result[category] = {}
            for brand, models in brands.items():
                result[category][brand] = {}
                for model, region_prices in models.items():
                    flat_prices = []
                    price_strs = []
                    for region, prices in region_prices.items():
                        if region == "_cleaned_id":
                            continue
                        if prices:
                            min_p = min(prices)
                            flat_prices.append(min_p)
                            price_strs.append(f"{region} - {min_p}")

                    if flat_prices:
                        result[category][brand][model] = [{
                            "product": model,
                            "name_std": f"{brand} {model}",
                            "min_price": min(flat_prices),
                            "prices": " / ".join(price_strs),
                            "price_count": len(flat_prices),
                            "cleaned_id": region_prices.get("_cleaned_id", 0)
                        }]

        return templates.TemplateResponse("matrix.html", {
            "request": request,
            "tree": result
        })

    except Exception as e:
        logger.exception("🔥 Ошибка в /matrix")
        return HTMLResponse(f"<h1>Ошибка</h1><pre>{str(e)}</pre>", status_code=500)


@router.post("/matrix/unlink")
def unlink_product(cleaned_id: int = Form(...)):
    session = get_session()
    try:
        row = session.execute(text("""
            SELECT name_std, brand, model, region
            FROM products_cleaned
            WHERE id = :id
        """), {"id": cleaned_id}).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Привязка не найдена")

        session.execute(text("DELETE FROM products_cleaned WHERE id = :id"), {"id": cleaned_id})
        session.execute(text("DELETE FROM products WHERE standard_id = :id"), {"id": cleaned_id})

        session.execute(text("""
            INSERT INTO unmatched_models (
                raw_name, source_channel, first_seen, sample_price,
                detected_brand, detected_model, detected_region, is_auto_detected
            ) VALUES (
                :raw_name, 'manual_unlinked', :now, 0, :brand, :model, :region, TRUE
            )
        """), {
            "raw_name": row.name_std,
            "now": datetime.now().isoformat(),
            "brand": row.brand,
            "model": row.model,
            "region": row.region
        })

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    return RedirectResponse(url="/matrix", status_code=303)

@router.get("/admin/clean-products")
def clean_invalid_cleaned_products():
    session = get_session()
    try:
        dangling = session.execute(text("""
            SELECT pc.id FROM products_cleaned pc
            LEFT JOIN catalog_products cp ON pc.catalog_product_id = cp.id
            WHERE cp.id IS NULL
        """)).fetchall()

        cleaned_ids = [row[0] for row in dangling]

        if cleaned_ids:
            session.execute(
                text("DELETE FROM products WHERE standard_id = ANY(:ids)"),
                {"ids": cleaned_ids}
            )
            session.execute(
                text("DELETE FROM products_cleaned WHERE id = ANY(:ids)"),
                {"ids": cleaned_ids}
            )

        session.commit()
        return JSONResponse({"ok": True, "deleted": len(cleaned_ids)})
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()
