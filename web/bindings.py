from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from database import get_session

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")

@router.get("/", response_class=HTMLResponse)
def view_bindings(request: Request):
    with get_session() as session:
        rows = session.execute(text("""
            SELECT pc.id AS cleaned_id, pc.name_std,
                   pc.brand, pc.lineup, pc.model, pc.region,
                   array_agg(p.name) AS linked_products
            FROM products_cleaned pc
            LEFT JOIN products p ON p.standard_id = pc.id
            GROUP BY pc.id
            ORDER BY pc.name_std
        """)).fetchall()

    data = [
        {
            "id": row.cleaned_id,
            "name_std": row.name_std,
            "brand": row.brand,
            "lineup": row.lineup,
            "model": row.model,
            "region": row.region,
            "linked": row.linked_products or []
        }
        for row in rows
    ]

    return templates.TemplateResponse("bindings.html", {"request": request, "bindings": data})

@router.post("/edit")
def edit_cleaned(
    cleaned_id: int = Form(...),
    brand: str = Form(...),
    lineup: str = Form(...),
    model: str = Form(...),
    region: str = Form(...),
    name_std: str = Form(...)
):
    with get_session() as session:
        session.execute(text("""
            UPDATE products_cleaned
            SET brand = :brand,
                lineup = :lineup,
                model = :model,
                region = :region,
                name_std = :name_std
            WHERE id = :id
        """), {
            "id": cleaned_id,
            "brand": brand,
            "lineup": lineup,
            "model": model,
            "region": region,
            "name_std": name_std
        })
        session.commit()
    return RedirectResponse(url="/bindings", status_code=303)

@router.post("/unlink")
def unlink_product(product_id: int = Form(...)):
    with get_session() as session:
        session.execute(text("DELETE FROM products WHERE id = :id"), {"id": product_id})
        session.commit()
    return RedirectResponse(url="/bindings", status_code=303)
