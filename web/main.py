from fastapi import FastAPI, Request, Query, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import asyncio
from utils import approve_message, get_unapproved_responses
from database import get_connection

app = FastAPI()

app.mount("/static", StaticFiles(directory="web/static"), name="static")
templates = Jinja2Templates(directory="web/templates")

@app.get("/review")
def review_responses(request: Request):
    responses = get_unapproved_responses()
    return templates.TemplateResponse("review_responses.html", {
        "request": request,
        "responses": responses
    })

@app.post("/review/submit")
def submit_response_review(message_id: int = Form(...), is_ok: str = Form(...)):
    approve_message(message_id, is_ok == "1")
    return RedirectResponse("/review", status_code=303)

@app.post("/clear")
async def clear_database(request: Request):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM prices")
            cur.execute("DELETE FROM products")
            conn.commit()

    return templates.TemplateResponse("index.html", {
        "request": request,
        "message": "✅ База данных очищена."
    })

def get_categories():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT name FROM products ORDER BY name ASC")
            return [row[0] for row in cur.fetchall()]

def get_available_countries(product_name):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('''
                SELECT DISTINCT p.country
                FROM prices p
                JOIN products prod ON p.product_id = prod.id
                WHERE prod.name = %s
                ORDER BY p.country
            ''', (product_name,))
            return [row[0] for row in cur.fetchall() if row[0]]

def get_prices_for_product(product_name, country=None, sort_by="price"):
    with get_connection() as conn:
        with conn.cursor() as cur:
            sort_column = "p.price" if sort_by == "price" else "p.message_date"
            if country:
                cur.execute(f'''
                    SELECT p.price, p.country, p.channel_name, p.message_date
                    FROM prices p
                    JOIN products prod ON p.product_id = prod.id
                    WHERE prod.name = %s AND p.country = %s
                    ORDER BY {sort_column} ASC
                ''', (product_name, country))
            else:
                cur.execute(f'''
                    SELECT p.price, p.country, p.channel_name, p.message_date
                    FROM prices p
                    JOIN products prod ON p.product_id = prod.id
                    WHERE prod.name = %s
                    ORDER BY {sort_column} ASC
                ''', (product_name,))
            return cur.fetchall()

def get_brand_overview():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('''
                SELECT split_part(prod.name, ' ', 1) AS brand, COUNT(DISTINCT prod.name) AS models
                FROM products prod
                GROUP BY brand
                ORDER BY models DESC
            ''')
            return cur.fetchall()

def get_products_by_brand(brand):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('''
                SELECT DISTINCT name FROM products
                WHERE name LIKE %s
                ORDER BY name ASC
            ''', (f'{brand} %',))
            return [row[0] for row in cur.fetchall()]

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    categories = get_categories()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "categories": categories,
        "review_link": "/review"
    })

@app.get("/product/{product_name}", response_class=HTMLResponse)
async def product_detail(request: Request, product_name: str, country: str = Query(default=None), sort: str = Query(default="price")):
    prices = get_prices_for_product(product_name, country, sort_by=sort)
    countries = get_available_countries(product_name)
    return templates.TemplateResponse("product.html", {
        "request": request,
        "product_name": product_name,
        "prices": prices,
        "available_countries": countries,
        "selected_country": country,
        "sort": sort
    })

@app.get("/brands", response_class=HTMLResponse)
async def brand_summary(request: Request):
    brands = get_brand_overview()
    return templates.TemplateResponse("brands.html", {
        "request": request,
        "brands": brands
    })

@app.get("/brand/{brand}", response_class=HTMLResponse)
async def brand_products(request: Request, brand: str):
    products = get_products_by_brand(brand)
    return templates.TemplateResponse("brand_products.html", {
        "request": request,
        "brand": brand,
        "products": products
    })
