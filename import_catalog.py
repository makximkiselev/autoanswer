import pandas as pd
from sqlalchemy import create_engine

# SQLAlchemy engine вместо psycopg2
engine = create_engine("postgresql+psycopg2://postgres:Sasuce0312@localhost:5432/autoanswer")
conn = engine.raw_connection()

# Путь к Excel-файлу
excel_path = "ПРАЙС_iBestBuy.xlsx"
df = pd.read_excel(excel_path)

def clean(s):
    return str(s).encode("utf-8", "ignore").decode("utf-8").strip()

cur = conn.cursor()
try:
    for _, row in df.iterrows():
        cat = clean(row["Категория"])
        brand = clean(row["Бренд"])
        model = clean(row["Модель"])
        product = clean(row["Наименование"])
        article = clean(row["Артикул"])

        # Категория
        cur.execute("SELECT id FROM categories WHERE name = %s", (cat,))
        cat_row = cur.fetchone()
        if not cat_row:
            cur.execute("INSERT INTO categories (name) VALUES (%s) RETURNING id", (cat,))
            cat_id = cur.fetchone()[0]
        else:
            cat_id = cat_row[0]

        # Бренд
        cur.execute("SELECT id FROM brands WHERE name = %s AND category_id = %s", (brand, cat_id))
        brand_row = cur.fetchone()
        if not brand_row:
            cur.execute("INSERT INTO brands (name, category_id) VALUES (%s, %s) RETURNING id", (brand, cat_id))
            brand_id = cur.fetchone()[0]
        else:
            brand_id = brand_row[0]

        # Модель
        cur.execute("SELECT id FROM models WHERE name = %s AND brand_id = %s", (model, brand_id))
        model_row = cur.fetchone()
        if not model_row:
            cur.execute("INSERT INTO models (name, brand_id) VALUES (%s, %s) RETURNING id", (model, brand_id))
            model_id = cur.fetchone()[0]
        else:
            model_id = model_row[0]

        # Товар
        cur.execute("SELECT id FROM catalog_products WHERE name = %s AND model_id = %s", (product, model_id))
        if not cur.fetchone():
            print(f"Inserting product: {product} | Article: {article} | Model ID: {model_id}")
            cur.execute(
                "INSERT INTO catalog_products (name, model_id, article) VALUES (%s, %s, %s)",
                (product, model_id, article)
            )

    conn.commit()
    print("✅ Импорт завершён успешно.")

finally:
    cur.close()
    conn.close()
