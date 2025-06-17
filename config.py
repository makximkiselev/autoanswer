from dotenv import load_dotenv
import os

load_dotenv()

API_ID_1 = int(os.getenv("API_ID_1"))
API_HASH_1 = os.getenv("API_HASH_1")
SESSION_NAME_1 = os.getenv("SESSION_NAME_1")
ACCOUNT_LABEL_1 = os.getenv("ACCOUNT_LABEL_1")


API_ID_2 = int(os.getenv("API_ID_2"))
API_HASH_2 = os.getenv("API_HASH_2")
SESSION_NAME_2 = os.getenv("SESSION_NAME_2")
ACCOUNT_LABEL_2 = os.getenv("ACCOUNT_LABEL_2")

API_TOKEN = os.getenv("API_TOKEN")

client_configs = [
    {
        "api_id": API_ID_1,
        "api_hash": API_HASH_1,
        "session": SESSION_NAME_1,
        "label": ACCOUNT_LABEL_1
    },
    {
        "api_id": API_ID_2,
        "api_hash": API_HASH_2,
        "session": SESSION_NAME_2,
        "label": ACCOUNT_LABEL_2
    }
]

POSTGRES_HOST = os.getenv("POSTGRES_HOST")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", 5432))
POSTGRES_DB = os.getenv("POSTGRES_DB")
POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
