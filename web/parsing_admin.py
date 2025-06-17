from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from database import get_connection

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")

@router.get("/manage-parsing", response_class=HTMLResponse)
def manage_parsing_view(request: Request):
    session = get_connection()
    try:
        lineups = session.execute(text("SELECT name FROM unknown_lineups ORDER BY name")).fetchall()
        exclusions = session.execute(text("SELECT phrase FROM exclusion_phrases ORDER BY phrase")).fetchall()
        unmatched = session.execute(text("""
            SELECT id, raw_name, price, source_channel, brand, model, region 
            FROM unmatched_models ORDER BY id DESC LIMIT 50
        """)).fetchall()

        return templates.TemplateResponse("manage_parsing.html", {
            "request": request,
            "lineups": [l[0] for l in lineups],
            "exclusions": [e[0] for e in exclusions],
            "unmatched": unmatched
        })
    finally:
        session.close()

@router.post("/manage-parsing/add-exclusion")
def add_exclusion(phrase: str = Form(...)):
    session = get_connection()
    session.execute(text("INSERT INTO exclusion_phrases (phrase) VALUES (:phrase) ON CONFLICT DO NOTHING"), {"phrase": phrase})
    session.commit()
    session.close()
    return RedirectResponse("/manage-parsing", status_code=303)

@router.post("/manage-parsing/delete-exclusion")
def delete_exclusion(phrase: str = Form(...)):
    session = get_connection()
    session.execute(text("DELETE FROM exclusion_phrases WHERE phrase = :phrase"), {"phrase": phrase})
    session.commit()
    session.close()
    return RedirectResponse("/manage-parsing", status_code=303)

@router.post("/manage-parsing/confirm-lineup")
def confirm_lineup(name: str = Form(...), brand: str = Form(...)):
    session = get_connection()
    session.execute(text("INSERT INTO lineups (name, brand) VALUES (:name, :brand) ON CONFLICT DO NOTHING"), {"name": name, "brand": brand})
    session.execute(text("DELETE FROM unknown_lineups WHERE name = :name"), {"name": name})
    session.commit()
    session.close()
    return RedirectResponse("/manage-parsing", status_code=303)
