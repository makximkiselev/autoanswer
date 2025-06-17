import os
from dotenv import load_dotenv

load_dotenv()

print("🔍 Проверка переменных окружения:")
print("BOT_TOKEN =", os.getenv("API_TOKEN"))
print("API_ID_1 =", os.getenv("API_ID_1"))
print("POSTGRES_USER =", os.getenv("POSTGRES_USER"))
print("POSTGRES_PASSWORD =", os.getenv("POSTGRES_PASSWORD"))
