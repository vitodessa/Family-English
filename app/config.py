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

# --- Speaking (голосовой собеседник) ---
# Мозг — Claude. Голос — ElevenLabs. Ключи только из окружения (.env), не в коде.
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
# Голос по умолчанию (Rachel) и быстрая модель. Можно поменять через окружение.
ELEVENLABS_VOICE_ID: str = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
ELEVENLABS_MODEL: str = os.getenv("ELEVENLABS_MODEL", "eleven_turbo_v2_5")


def speaking_enabled() -> bool:
    """Модуль доступен только когда заданы оба ключа."""
    return bool(ANTHROPIC_API_KEY and ELEVENLABS_API_KEY)
