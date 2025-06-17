from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from database import get_session
import os
import uuid

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")

@router.get("/catalog", response_class=HTMLResponse)
def catalog_main(request: Request):
    with get_session() as session:
        categories = session.execute(text("SELECT id, name FROM categories ORDER BY name")).fetchall()
    return templates.TemplateResponse("catalog.html", {"request": request, "categories": categories})

@router.get("/catalog/brands/{category_id}", response_class=HTMLResponse)
def catalog_brands(request: Request, category_id: int):
    with get_session() as session:
        brands = session.execute(text("SELECT id, name FROM brands WHERE category_id = :id ORDER BY name"), {"id": category_id}).fetchall()
    return templates.TemplateResponse("partials/brands.html", {"request": request, "brands": brands})

@router.get("/catalog/products/{brand_id}", response_class=HTMLResponse)
def catalog_products(request: Request, brand_id: int):
    with get_session() as session:
        products = session.execute(text("""
            SELECT cp.id, cp.name, cp.article
            FROM catalog_products cp
            JOIN models mo ON cp.model_id = mo.id
            WHERE mo.brand_id = :id
            ORDER BY cp.name
        """), {"id": brand_id}).fetchall()
    return templates.TemplateResponse("partials/products.html", {"request": request, "products": products})

@router.get("/catalog/product/{product_id}", response_class=HTMLResponse)
def catalog_product_detail(request: Request, product_id: int):
    with get_session() as session:
        row = session.execute(text("""
            SELECT cp.name, cp.article,
                   mo.name AS model, br.name AS brand, ca.name AS category,
                   ca.id AS category_id
            FROM catalog_products cp
            JOIN models mo ON cp.model_id = mo.id
            JOIN brands br ON mo.brand_id = br.id
            JOIN categories ca ON br.category_id = ca.id
            WHERE cp.id = :id
        """), {"id": product_id}).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Товар не найден")

        prices = session.execute(text("""
            SELECT pr.price, pr.updated_at
            FROM prices pr
            JOIN products p ON pr.product_id = p.id
            WHERE p.standard_id = (
                SELECT pc.id FROM products_cleaned pc WHERE pc.catalog_product_id = :id
            )
            ORDER BY pr.updated_at DESC
        """), {"id": product_id}).fetchall()

        images = session.execute(text("SELECT url FROM product_images WHERE product_id = :id ORDER BY sort_order, id"), {"id": product_id}).fetchall()
        links = session.execute(text("SELECT url FROM product_links WHERE product_id = :id"), {"id": product_id}).fetchall()

        features = session.execute(text("""
            SELECT mf.name, pf.value
            FROM master_features mf
            LEFT JOIN product_features pf 
                ON mf.id = pf.feature_id AND pf.product_id = :product_id
            WHERE mf.category_id = :category_id
            ORDER BY mf.sort_order
        """), {
            "product_id": product_id,
            "category_id": row.category_id
        }).fetchall()

    return templates.TemplateResponse("product_detail.html", {
        "request": request,
        "product": {
            "id": product_id,
            "name": row.name,
            "article": row.article,
            "category": row.category,
            "brand": row.brand,
            "model": row.model,
            "images": [i.url for i in images],
            "links": [l.url for l in links]
        },
        "prices": prices,
        "features": features
    })

@router.get("/catalog/product/{product_id}/edit", response_class=HTMLResponse)
def edit_product(request: Request, product_id: int):
    with get_session() as session:
        row = session.execute(text("""
            SELECT cp.name, cp.article,
                   ca.id AS category_id
            FROM catalog_products cp
            JOIN models mo ON cp.model_id = mo.id
            JOIN brands br ON mo.brand_id = br.id
            JOIN categories ca ON br.category_id = ca.id
            WHERE cp.id = :id
        """), {"id": product_id}).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Товар не найден")

        images = session.execute(text("SELECT url FROM product_images WHERE product_id = :id ORDER BY sort_order, id"), {"id": product_id}).fetchall()
        links = session.execute(text("SELECT url FROM product_links WHERE product_id = :id"), {"id": product_id}).fetchall()

        features = session.execute(text("""
            SELECT mf.id AS feature_id, mf.name, pf.value
            FROM master_features mf
            LEFT JOIN product_features pf ON mf.id = pf.feature_id AND pf.product_id = :pid
            WHERE mf.category_id = :cid
            ORDER BY mf.sort_order
        """), {
            "pid": product_id,
            "cid": row.category_id
        }).fetchall()

    return templates.TemplateResponse("product_edit.html", {
        "request": request,
        "product": {
            "id": product_id,
            "name": row.name,
            "article": row.article,
            "images": [i.url for i in images],
            "links": [l.url for l in links],
            "features": features
        }
    })


@router.post("/catalog/product/{product_id}/edit")
async def update_product(
    request: Request,
    product_id: int,
    name: str = Form(...),
    article: str = Form(""),
    image_urls: list[str] = Form([]),
    links: list[str] = Form([]),
    image_files: list[UploadFile] = File(default=[])
):
    form = await request.form()

    upload_dir = "static/uploads"
    os.makedirs(upload_dir, exist_ok=True)

    uploaded_urls = []
    for file in image_files:
        if file.filename:
            ext = os.path.splitext(file.filename)[1]
            safe_name = f"{uuid.uuid4().hex}{ext}"
            file_path = os.path.join(upload_dir, safe_name)

            with open(file_path, "wb") as f:
                content = await file.read()
                f.write(content)

            uploaded_urls.append(f"/static/uploads/{safe_name}")

    all_images = image_urls + uploaded_urls

    with get_session() as session:
        # Обновляем основную информацию
        session.execute(text("""
            UPDATE catalog_products
            SET name = :name, article = :article
            WHERE id = :id
        """), {"name": name, "article": article, "id": product_id})

        # Удаляем старые изображения
        session.execute(text("DELETE FROM product_images WHERE product_id = :id"), {"id": product_id})
        for idx, url in enumerate(all_images):
            session.execute(text("""
                INSERT INTO product_images (product_id, url, sort_order)
                VALUES (:pid, :url, :ord)
            """), {"pid": product_id, "url": url, "ord": idx})

        # Удаляем старые ссылки
        session.execute(text("DELETE FROM product_links WHERE product_id = :id"), {"id": product_id})
        for url in links:
            session.execute(text("""
                INSERT INTO product_links (product_id, url)
                VALUES (:pid, :url)
            """), {"pid": product_id, "url": url})

        # Удаляем старые характеристики
        session.execute(text("DELETE FROM product_features WHERE product_id = :id"), {"id": product_id})

        # Добавляем новые характеристики из формы
        for key in form:
            if key.startswith("feature_"):
                feature_id = key.split("_")[1]
                value = form.get(key)
                if value:
                    session.execute(text("""
                        INSERT INTO product_features (product_id, feature_id, value)
                        VALUES (:pid, :fid, :val)
                    """), {"pid": product_id, "fid": feature_id, "val": value})

        session.commit()

    return RedirectResponse(url=f"/catalog/product/{product_id}", status_code=303)

