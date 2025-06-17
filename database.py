from sqlalchemy import create_engine, text, Column, Integer, String, Boolean, BigInteger, TIMESTAMP, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from contextlib import contextmanager
from typing import List, Optional
from datetime import datetime
import os

DB_NAME = os.getenv("POSTGRES_DB", "autoanswer")
DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "Sasuce0312")
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_connection():
    return SessionLocal()

class ProductCleaned(Base):
    __tablename__ = "products_cleaned"
    id = Column(Integer, primary_key=True)
    brand = Column(String)
    lineup = Column(String)
    model = Column(String)
    region = Column(String)
    name_std = Column(String, unique=True)
    catalog_product_id = Column(Integer, ForeignKey("catalog_products.id"))


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    standard_id = Column(Integer, ForeignKey("products_cleaned.id"))
    standard = relationship("ProductCleaned")

class Price(Base):
    __tablename__ = "prices"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    price = Column(Integer)
    country = Column(String)
    source_account = Column(String)
    channel_name = Column(String)
    message_id = Column(Integer)
    message_date = Column(String)

class SourceID(Base):
    __tablename__ = "source_ids"
    id = Column(Integer, primary_key=True)
    channel_id = Column(BigInteger, unique=True)
    name = Column(String)
    type = Column(String)
    monitored = Column(Boolean, default=True)

class UnmatchedModel(Base):
    __tablename__ = "unmatched_models"
    id = Column(Integer, primary_key=True)
    raw_name = Column(String)
    source_channel = Column(String)
    first_seen = Column(String)
    sample_price = Column(Integer)

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    chat_id = Column(BigInteger)
    user_id = Column(BigInteger)
    username = Column(String)
    text = Column(String)
    timestamp = Column(String)
    account_id = Column(String)
    direction = Column(String, default="incoming")
    approved = Column(Boolean, default=None)

class ProcessedChannel(Base):
    __tablename__ = "processed_channels"
    channel_id = Column(BigInteger, primary_key=True)
    account_id = Column(String)
    processed_at = Column(TIMESTAMP)

def init_db():
    Base.metadata.create_all(bind=engine)

    session = get_connection()
    try:
        session.execute(text("""
            ALTER TABLE products
            ADD COLUMN IF NOT EXISTS approved BOOLEAN DEFAULT FALSE
        """))

        session.execute(text("""
            CREATE TABLE IF NOT EXISTS categories (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL
            );

            CREATE TABLE IF NOT EXISTS brands (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                category_id INTEGER REFERENCES categories(id)
            );

            CREATE TABLE IF NOT EXISTS models (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                brand_id INTEGER REFERENCES brands(id)
            );

            CREATE TABLE IF NOT EXISTS catalog_products (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                model_id INTEGER REFERENCES models(id),
                article TEXT
            );
        """))

        session.commit()
    finally:
        session.close()

def insert_product_if_new(name: str, standard_id: int) -> int:
    session = get_connection()
    try:
        existing = session.query(Product).filter_by(name=name, standard_id=standard_id).first()
        if existing:
            return existing.id

        new_product = Product(name=name, standard_id=standard_id)
        session.add(new_product)
        session.commit()
        session.refresh(new_product)
        return new_product.id
    finally:
        session.close()

def save_source_id(source_telegram_id: int, name: str, type_: str):
    session = get_connection()
    try:
        session.execute(
            text("""
                INSERT INTO source_ids (channel_id, name, type, monitored)
                VALUES (:channel_id, :name, :type, TRUE)
                ON CONFLICT (channel_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    type = EXCLUDED.type,
                    monitored = TRUE
            """),
            {"channel_id": source_telegram_id, "name": name, "type": type_}
        )
        session.commit()
    finally:
        session.close()

def get_allowed_sources(source_type=None, account_label=None):
    session = get_connection()
    try:
        query = "SELECT * FROM source_ids"
        conditions = []
        params = {}

        if source_type:
            conditions.append("type = :source_type")
            params["source_type"] = source_type
        if account_label:
            conditions.append("account_id = :account_label")
            params["account_label"] = account_label

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        result = session.execute(text(query), params)
        return [dict(row._mapping) for row in result.fetchall()]
    finally:
        session.close()

def get_allowed_sources_by_id(type_: Optional[str] = None, account_id: Optional[str] = None) -> List[int]:
    session = get_connection()
    try:
        if account_id:
            if type_:
                result = session.execute(
                    text("""
                        SELECT channel_id FROM source_ids
                        WHERE monitored = true AND type = :type AND account_id = :account_id
                    """),
                    {"type": type_, "account_id": account_id}
                )
            else:
                result = session.execute(
                    text("""
                        SELECT channel_id FROM source_ids
                        WHERE monitored = true AND account_id = :account_id AND (type = 'channel' OR type = 'chat_prices')
                    """),
                    {"account_id": account_id}
                )
        else:
            if type_:
                result = session.execute(
                    text("SELECT channel_id FROM source_ids WHERE monitored = true AND type = :type"),
                    {"type": type_}
                )
            else:
                result = session.execute(
                    text("""
                        SELECT channel_id FROM source_ids
                        WHERE monitored = true AND (type = 'channel' OR type = 'chat_prices')
                    """)
                )
        return [row[0] for row in result.fetchall()]
    finally:
        session.close()

@contextmanager
def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

def save_unmatched_model(raw_name: str, source_channel: str, price: int, brand=None, model=None, region=None, is_auto=False):
    session = get_connection()
    try:
        # Не дублируем
        exists = session.execute(
            text("SELECT 1 FROM unmatched_models WHERE raw_name = :raw_name AND source_channel = :source_channel"),
            {"raw_name": raw_name, "source_channel": source_channel}
        ).first()
        if exists:
            return

        # Сохраняем без region_flag
        session.execute(
            text("""
                INSERT INTO unmatched_models (
                    raw_name, source_channel, first_seen, sample_price,
                    detected_brand, detected_model, detected_region,
                    is_auto_detected
                )
                VALUES (
                    :raw_name, :source_channel, :first_seen, :sample_price,
                    :detected_brand, :detected_model, :detected_region,
                    :is_auto_detected
                )
            """),
            {
                "raw_name": raw_name,
                "source_channel": source_channel,
                "first_seen": datetime.now().isoformat(),
                "sample_price": price,
                "detected_brand": brand,
                "detected_model": model,
                "detected_region": region,
                "is_auto_detected": is_auto
            }
        )
        session.commit()
    finally:
        session.close()

def was_channel_processed(channel_id: int, account_id: str) -> bool:
    session = get_connection()
    try:
        result = session.execute(
            text("""
                SELECT 1 FROM processed_channels 
                WHERE channel_id = :channel_id AND account_id = :account_id
            """),
            {"channel_id": channel_id, "account_id": account_id}
        ).first()
        return result is not None
    finally:
        session.close()


def add_processed_channel(channel_id: int, account_id: str):
    session = get_connection()
    try:
        session.execute(
            text("""
                INSERT INTO processed_channels (channel_id, account_id, processed_at)
                VALUES (:channel_id, :account_id, CURRENT_TIMESTAMP)
                ON CONFLICT DO NOTHING
            """),
            {"channel_id": channel_id, "account_id": account_id}
        )
        session.commit()
    finally:
        session.close()

def get_region_map() -> dict:
    with get_session() as session:
        rows = session.execute(text("SELECT flag, code FROM regions")).fetchall()
        return {flag: code for flag, code in rows}