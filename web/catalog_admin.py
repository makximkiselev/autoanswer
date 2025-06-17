import os
import uuid
from fastapi import APIRouter, Request, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy import text
from database import get_session

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")

class ReorderRequest(BaseModel):
    ids: List[int]


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@router.get("/catalog/edit", response_class=HTMLResponse)
def catalog_edit(request: Request):
    view = request.query_params.get("view", "categories")

    with get_session() as session:
        categories = session.execute(text("SELECT id, name, parent_id FROM categories ORDER BY name")).fetchall()
        brands = session.execute(text("SELECT id, name FROM brands ORDER BY name")).fetchall()
        models = session.execute(text("SELECT id, name, brand_id FROM models ORDER BY name")).fetchall()
        products = session.execute(text("SELECT id, name, model_id, article FROM catalog_products ORDER BY name")).fetchall()

    category_map = {}
    children_map = {}
    for cat in categories:
        category_map[cat.id] = {"id": cat.id, "name": cat.name, "parent_id": cat.parent_id, "brands": [], "children": []}
        children_map.setdefault(cat.parent_id, []).append(cat.id)

    for cat_id, cat in category_map.items():
        cat["children"] = [category_map[cid] for cid in children_map.get(cat_id, [])]

    brand_map = {}
    model_map = {}

    for brand in brands:
        brand_map[brand.id] = {"id": brand.id, "name": brand.name, "models": []}

    for model in models:
        m = {"id": model.id, "name": model.name, "products": []}
        model_map[model.id] = m
        if model.brand_id in brand_map:
            brand_map[model.brand_id]["models"].append(m)

    for product in products:
        p = {"id": product.id, "name": product.name, "article": product.article}
        if product.model_id in model_map:
            model_map[product.model_id]["products"].append(p)

    root_categories = [cat for cat in category_map.values() if cat["parent_id"] is None]

    return templates.TemplateResponse("catalog_edit.html", {
        "request": request,
        "categories": root_categories,
        "brands": list(brand_map.values()),
        "models": list(model_map.values()),
        "view": view
    })

@router.get("/catalog/subcategories/{category_id}")
def get_subcategories(category_id: int):
    with get_session() as session:
        subcategories = session.execute(
            text("SELECT id, name, parent_id FROM categories WHERE parent_id = :cat_id ORDER BY sort_order"),
            {"cat_id": category_id}
        ).fetchall()

        brands = session.execute(
            text("""
                SELECT b.id, b.name
                FROM brands b
                JOIN brand_category bc ON b.id = bc.brand_id
                WHERE bc.category_id = :cat_id
                ORDER BY b.name
            """),
            {"cat_id": category_id}
        ).fetchall()

        return {
            "subcategories": [{"id": row.id, "name": row.name, "parent_id": row.parent_id} for row in subcategories],
            "brands": [{"id": row.id, "name": row.name} for row in brands],
        }


@router.get("/catalog/brands/{subcategory_id}")
def get_brands(subcategory_id: int):
    with get_session() as session:
        brands = session.execute(
            text("""
                SELECT b.id, b.name
                FROM brands b
                JOIN brand_category bc ON b.id = bc.brand_id
                WHERE bc.category_id = :cat_id
                ORDER BY b.name
            """),
            {"cat_id": subcategory_id}
        ).fetchall()

        return JSONResponse({
            "brands": [{"id": b.id, "name": b.name} for b in brands]
        })

@router.post("/catalog/edit/add-category")
def add_category(name: str = Form(...), parent_id: Optional[int] = Form(None)):
    with get_session() as session:
        session.execute(
            text("INSERT INTO categories (name, parent_id) VALUES (:name, :parent_id)"),
            {"name": name, "parent_id": parent_id}
        )
        session.commit()
    return RedirectResponse(url="/catalog/edit", status_code=303)

@router.post("/catalog/edit/rename-category")
def rename_category(category_id: int = Form(...), new_name: str = Form(...)):
    with get_session() as session:
        session.execute(
            text("UPDATE categories SET name = :name WHERE id = :id"),
            {"name": new_name, "id": category_id}
        )
        session.commit()
    return RedirectResponse(url="/catalog/edit", status_code=303)

@router.post("/catalog/edit/delete-category")
def delete_category(category_id: int = Form(...)):
    with get_session() as session:
        session.execute(text("DELETE FROM categories WHERE id = :id"), {"id": category_id})
        session.commit()
    return RedirectResponse(url="/catalog/edit", status_code=303)

@router.post("/catalog/move-category")
def move_category(category_id: int = Form(...), new_parent_id: int = Form(None)):
    if category_id == new_parent_id:
        raise HTTPException(status_code=400, detail="Категория не может быть родителем сама себе")

    with get_session() as session:
        # проверка на циклическую вложенность
        def is_descendant(child_id, parent_id):
            if parent_id is None:
                return False
            current = parent_id
            while current is not None:
                res = session.execute(text("SELECT parent_id FROM categories WHERE id = :id"), {"id": current}).fetchone()
                if res is None:
                    break
                if res[0] == child_id:
                    return True
                current = res[0]
            return False

        if is_descendant(category_id, new_parent_id):
            raise HTTPException(status_code=400, detail="Невозможно поместить родительскую категорию в одну из своих подкатегорий")

        session.execute(
            text("UPDATE categories SET parent_id = :new_parent_id WHERE id = :category_id"),
            {"category_id": category_id, "new_parent_id": new_parent_id}
        )
        session.commit()
    return JSONResponse({"status": "ok"})

@router.post("/catalog/edit/add-brand")
def add_brand(name: str = Form(...)):
    with get_session() as session:
        result = session.execute(
            text("INSERT INTO brands (name) VALUES (:name) RETURNING id"),
            {"name": name}
        )
        session.commit()
        brand_id = result.scalar()
    return JSONResponse({"id": brand_id, "name": name})  # <-- важно

@router.post("/catalog/edit/link-brand-to-category")
def link_brand_to_category(brand_id: int = Form(...), category_id: int = Form(...)):
    with get_session() as session:
        session.execute(
            text("""
                INSERT INTO brand_category (brand_id, category_id)
                VALUES (:brand_id, :category_id)
                ON CONFLICT DO NOTHING
            """),
            {"brand_id": brand_id, "category_id": category_id}
        )
        session.commit()
    return JSONResponse({"status": "ok"})



@router.post("/catalog/edit/rename-brand")
def rename_brand(brand_id: int = Form(...), new_name: str = Form(...)):
    with get_session() as session:
        session.execute(
            text("UPDATE brands SET name = :name WHERE id = :id"),
            {"name": new_name, "id": brand_id}
        )
        session.commit()
    return RedirectResponse(url="/catalog/edit", status_code=303)

@router.post("/catalog/edit/delete-brand")
def delete_brand(brand_id: int = Form(...)):
    with get_session() as session:
        session.execute(text("DELETE FROM brands WHERE id = :id"), {"id": brand_id})
        session.commit()
    return RedirectResponse(url="/catalog/edit", status_code=303)

@router.post("/catalog/edit/add-model")
def add_model(name: str = Form(...), brand_id: int = Form(...)):
    with get_session() as session:
        category_id = session.execute(
            text("SELECT category_id FROM brands WHERE id = :id"),
            {"id": brand_id}
        ).scalar()

        result = session.execute(
            text("""
                INSERT INTO models (name, brand_id, category_id)
                VALUES (:name, :brand_id, :category_id)
                RETURNING id
            """),
            {"name": name, "brand_id": brand_id, "category_id": category_id}
        )
        session.commit()
        new_id = result.scalar()
    return JSONResponse({"id": new_id, "name": name})


@router.post("/catalog/edit/rename-model")
def rename_model(model_id: int = Form(...), new_name: str = Form(...)):
    with get_session() as session:
        session.execute(
            text("UPDATE models SET name = :name WHERE id = :id"),
            {"name": new_name, "id": model_id}
        )
        session.commit()
    return RedirectResponse(url="/catalog/edit", status_code=303)

@router.post("/catalog/edit/delete-model")
def delete_model(model_id: int = Form(...)):
    with get_session() as session:
        session.execute(text("DELETE FROM models WHERE id = :id"), {"id": model_id})
        session.commit()
    return RedirectResponse(url="/catalog/edit", status_code=303)

@router.post("/catalog/edit/add-product")
def add_product(name: str = Form(...), model_id: int = Form(...)):
    with get_session() as session:
        product_id = session.execute(
            text("INSERT INTO catalog_products (name, model_id) VALUES (:name, :model_id) RETURNING id"),
            {"name": name, "model_id": model_id}
        ).scalar()

        row = session.execute(text("""
            SELECT mo.name AS model_name, br.name AS brand_name, ca.name AS category_name
            FROM models mo
            JOIN brands br ON mo.brand_id = br.id
            JOIN categories ca ON br.category_id = ca.id
            WHERE mo.id = :model_id
        """), {"model_id": model_id}).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Модель не найдена")

        from utils import generate_article
        article = generate_article(row.category_name, row.brand_name, row.model_name, product_id)

        session.execute(text("UPDATE catalog_products SET article = :article WHERE id = :id"),
                        {"article": article, "id": product_id})

        session.commit()
    return RedirectResponse(url="/catalog/edit", status_code=303)

@router.post("/catalog/edit/rename-product")
def rename_product(product_id: int = Form(...), new_name: str = Form(...)):
    with get_session() as session:
        session.execute(
            text("UPDATE catalog_products SET name = :name WHERE id = :id"),
            {"name": new_name, "id": product_id}
        )
        session.commit()
    return RedirectResponse(url="/catalog/edit", status_code=303)

@router.post("/catalog/edit/delete-product")
def delete_product(product_id: int = Form(...)):
    with get_session() as session:
        session.execute(text("DELETE FROM catalog_products WHERE id = :id"), {"id": product_id})
        session.commit()
    return RedirectResponse(url="/catalog/edit", status_code=303)

@router.post("/catalog/reorder/{container_id}")
async def reorder_items(container_id: str, body: ReorderRequest):
    table_map = {
        "categories": "categories",
        "subcategories": "categories",
        "brands": "brands",
        "models": "models"
    }
    table = table_map.get(container_id)
    if not table:
        return JSONResponse(status_code=400, content={"error": "Неверный тип контейнера"})

    with get_session() as session:
        for position, item_id in enumerate(body.ids):
            session.execute(
                text(f"UPDATE {table} SET position = :pos WHERE id = :id"),
                {"pos": position, "id": item_id}
            )
        session.commit()
    return {"status": "ok"}

@router.get("/catalog/categories-json")
def get_all_categories():
    with get_session() as session:
        rows = session.execute(text("SELECT id, name, parent_id FROM categories")).fetchall()
        return [{"id": r.id, "name": r.name, "parent_id": r.parent_id} for r in rows]
