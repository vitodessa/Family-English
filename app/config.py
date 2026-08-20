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

# --- Прогрессия карточек (v2): индивидуальный старт от уровня + долив по мере изучения ---
LESSON_CARDS: int = int(os.getenv("LESSON_CARDS", "5"))       # повторений для шага «Карточки» в уроке дня
START_CARDS: int = int(os.getenv("START_CARDS", "10"))        # выдать на старте
WARMUP_CARDS: int = int(os.getenv("WARMUP_CARDS", "8"))       # простых A1 «на разогрев» для уровней выше A1
DECK_LOW_WATER: int = int(os.getenv("DECK_LOW_WATER", "5"))   # порог «свежих» карточек, ниже которого доливаем
TOPUP_CARDS: int = int(os.getenv("TOPUP_CARDS", "10"))        # сколько добавлять за один долив

# Уровни CEFR в порядке возрастания — используется при подборе слов.
CEFR_ORDER = ["A1", "A2", "B1", "B2", "C1", "C2"]

# --- Speaking (голосовой собеседник) ---
# Мозг — Claude. Голос — ElevenLabs. Ключи только из окружения (.env), не в коде.
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
# Дешёвая быстрая модель для простых задач (перевод слова при чтении). Пусто/не задано —
# берём основную (безопасно); можно указать Haiku через окружение ради скорости и экономии.
ANTHROPIC_MODEL_CHEAP: str = os.getenv("ANTHROPIC_MODEL_CHEAP") or ANTHROPIC_MODEL

ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
# Голос по умолчанию (Rachel) и быстрая модель. Можно поменять через окружение.
ELEVENLABS_VOICE_ID: str = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
ELEVENLABS_MODEL: str = os.getenv("ELEVENLABS_MODEL", "eleven_turbo_v2_5")


def speaking_enabled() -> bool:
    """Модуль доступен только когда заданы оба ключа."""
    return bool(ANTHROPIC_API_KEY and ELEVENLABS_API_KEY)


def reading_enabled() -> bool:
    """Чтению нужен только Claude (генерация текста + перевод слова)."""
    return bool(ANTHROPIC_API_KEY)


def writing_enabled() -> bool:
    """Письму нужен только Claude (разбор написанного)."""
    return bool(ANTHROPIC_API_KEY)


def grammar_enabled() -> bool:
    """Грамматике нужен только Claude (теория + клоуз-практика)."""
    return bool(ANTHROPIC_API_KEY)


# --- Отчёт родителю через Telegram-бота ---
# Токен бота из BotFather и chat_id семейного/родительского чата.
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")


def reporting_enabled() -> bool:
    """Отчёты уходят, только когда заданы токен бота и chat_id."""
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
