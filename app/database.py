"""Подключение к БД и сессии. Драйвер выбирается по DATABASE_URL."""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import DATABASE_URL

# Для SQLite создаём папку под файл БД (это и есть «постоянный диск»).
if DATABASE_URL.startswith("sqlite"):
    db_path = DATABASE_URL.replace("sqlite:///", "", 1)
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    connect_args = {"check_same_thread": False}
else:
    connect_args = {}

engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    future=True,
)

Base = declarative_base()


def get_db():
    """Зависимость FastAPI: одна сессia на запрос, гарантированно закрывается."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
