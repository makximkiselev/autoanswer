from logging.config import fileConfig
from sqlalchemy import create_engine, pool
from alembic import context
import sys
import os

# Добавим путь к корню проекта, чтобы импортировать `database`
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database import Base  # обязательно чтобы в database.py был Base = declarative_base()

# Config for logging
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Прямая строка подключения
# Получаем строку подключения из alembic.ini
DATABASE_URL = config.get_main_option("sqlalchemy.url")


target_metadata = Base.metadata


def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode."""
    connectable = create_engine(DATABASE_URL, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
