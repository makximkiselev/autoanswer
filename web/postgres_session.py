# postgres_session.py

from telethon.sessions import AbstractSession
import pickle
import psycopg2
import os
from database import get_connection

class PostgreSQLSession(AbstractSession):
    def __init__(self, session_name: str):
        super().__init__()
        self.session_name = session_name
        self._load()

    def _load(self):
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS telethon_sessions (
                        session_name TEXT PRIMARY KEY,
                        session_data BYTEA
                    )
                """)
                conn.commit()

                cur.execute("SELECT session_data FROM telethon_sessions WHERE session_name = %s", (self.session_name,))
                row = cur.fetchone()
                if row:
                    try:
                        self._dc_id, self._server_address, self._port, self.auth_key = pickle.loads(row[0])
                    except Exception as e:
                        print(f"Ошибка при загрузке сессии: {e}")

    def save(self):
        data = pickle.dumps((self._dc_id, self._server_address, self._port, self.auth_key))
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO telethon_sessions (session_name, session_data)
                    VALUES (%s, %s)
                    ON CONFLICT (session_name)
                    DO UPDATE SET session_data = EXCLUDED.session_data
                """, (self.session_name, data))
                conn.commit()

    def delete(self):
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM telethon_sessions WHERE session_name = %s", (self.session_name,))
                conn.commit()
