# database.py

import psycopg2
from psycopg2.extras import RealDictCursor
from sqlalchemy.orm import declarative_base
import os

DB_NAME = os.getenv("POSTGRES_DB", "price_parser")
DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "Sasuce0312")
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")

Base = declarative_base()

def get_connection():
    return psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        cursor_factory=RealDictCursor
    )

def insert_product_if_new(name: str, standard_id: int) -> int:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM products WHERE name = %s AND standard_id = %s",
                (name, standard_id)
            )
            result = cursor.fetchone()
            if result:
                return result[0]

            cursor.execute(
                "INSERT INTO products (name, standard_id) VALUES (%s, %s) RETURNING id",
                (name, standard_id)
            )
            product_id = cursor.fetchone()[0]
            conn.commit()
            return product_id

def init_db():
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Создание таблицы products_cleaned
            cur.execute('''
                CREATE TABLE IF NOT EXISTS products_cleaned (
                    id SERIAL PRIMARY KEY,
                    brand TEXT,
                    lineup TEXT,
                    model TEXT,
                    region TEXT,
                    name_std TEXT UNIQUE
                )
            ''')

            # Создание таблицы unmatched_models
            cur.execute('''
                CREATE TABLE IF NOT EXISTS unmatched_models (
                    id SERIAL PRIMARY KEY,
                    raw_name TEXT,
                    source_channel TEXT,
                    first_seen TEXT,
                    sample_price INTEGER
                )
            ''')

            # Создание таблицы products
            cur.execute('''
                CREATE TABLE IF NOT EXISTS products (
                    id SERIAL PRIMARY KEY,
                    name TEXT,
                    standard_id INTEGER REFERENCES products_cleaned(id)
                )
            ''')

            # Создание таблицы prices
            cur.execute('''
                CREATE TABLE IF NOT EXISTS prices (
                    id SERIAL PRIMARY KEY,
                    product_id INTEGER REFERENCES products(id),
                    price INTEGER,
                    country TEXT,
                    source_account TEXT,
                    channel_name TEXT,
                    message_id INTEGER,
                    message_date TEXT
                )
            ''')

            # Создание таблицы messages
            cur.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT,
                    user_id BIGINT,
                    username TEXT,
                    text TEXT,
                    timestamp TEXT,
                    account_id TEXT,
                    direction TEXT DEFAULT 'incoming',
                    approved BOOLEAN DEFAULT NULL
                )
            ''')

            # На случай, если старые таблицы без direction
            cur.execute('''
                ALTER TABLE messages
                ADD COLUMN IF NOT EXISTS direction TEXT DEFAULT 'incoming'
            ''')

            cur.execute('''
                CREATE TABLE IF NOT EXISTS source_ids (
                    id BIGINT PRIMARY KEY,
                    name TEXT,
                    type TEXT
                )
            ''')

        conn.commit()

def save_source_id(source_id: int, name: str, type_: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO source_ids (id, name, type)
                VALUES (%s, %s, %s)
                ON CONFLICT (id) DO NOTHING
            """, (source_id, name, type_))
        conn.commit()

def get_allowed_sources(type_: str) -> list:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM source_ids WHERE type = %s", (type_,))
            return [row["id"] for row in cur.fetchall()]

