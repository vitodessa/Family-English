"""Настройки приложения. Секреты берутся из окружения, не из кода."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

APP_TITLE = "Family English"

SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-insecure-change-me")

DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "sqlite:///" + str(BASE_DIR / "data" / "family.db"),
)

ADMIN_NAME: str = os.getenv("ADMIN_NAME", "admin")
ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "")

INITIAL_CARDS: int = int(os.getenv("INITIAL_CARDS", "20"))

# Уровни CEFR в порядке возрастания — используется при подборе слов.
CEFR_ORDER = ["A1", "A2", "B1", "B2", "C1", "C2"]
