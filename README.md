# Price Parser Bot

Telegram-бот и парсер цен из Telegram-каналов с поддержкой LLM и PostgreSQL.

## 🚀 Быстрый старт

1. Установите зависимости:
```bash
pip install -r requirements.txt
```

2. Создайте файл `.env` (он уже есть в этом проекте):
```env
TELEGRAM_API_ID=...
TELEGRAM_API_HASH=...
BOT_TOKEN=...
DATABASE_URL=postgresql://...
```

3. Примените миграции базы данных:
```bash
alembic upgrade head
```

4. Запустите бота:
```bash
python main.py
```

## 📁 Структура проекта

- `main.py` — запуск бота
- `parser.py` — парсинг сообщений из Telegram
- `llm.py` — взаимодействие с нейросетью
- `config.py`, `.env` — конфигурационные файлы
- `alembic/` — миграции PostgreSQL
- `sessions/` — данные Telethon (игнорируются в Git)

## ⚙️ Зависимости

Убедитесь, что у вас установлен Python 3.11+. Далее создайте `requirements.txt`:
```bash
pip freeze > requirements.txt
```