CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    country TEXT
);

CREATE TABLE IF NOT EXISTS prices (
    id SERIAL PRIMARY KEY,
    product_id INTEGER REFERENCES products(id),
    price REAL NOT NULL,
    channel_name TEXT,
    message_id BIGINT,
    message_date TIMESTAMP,
    UNIQUE(product_id, channel_name, message_id)
);

CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT,
    user_id BIGINT,
    username TEXT,
    text TEXT,
    timestamp TIMESTAMP,
    account_id TEXT,
    is_approved BOOLEAN DEFAULT NULL
);
