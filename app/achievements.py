"""Ачивки — считаются из накопленных данных (без API). Только отображение."""

from datetime import datetime

from app import token_service
from app.models import LearningEvent
from app.models import Session as ConvSession

# key: (иконка, название, описание, порог/условие-тег)
_DEFS = [
    ("start", "🌱", "Первые шаги", "Сделай первое повторение"),
    ("rev100", "📗", "Сотня", "100 повторений всего"),
    ("rev500", "🏆", "Пятьсот", "500 повторений всего"),
    ("streak7", "🔥", "Неделя подряд", "Урок дня 7 дней подряд"),
    ("lesson", "✅", "Первый урок", "Пройди Урок дня целиком"),
    ("speaking", "🎤", "Заговорил", "Первый разговор с AI"),
    ("writing", "✍️", "Писатель", "Первое письмо"),
    ("reading", "📖", "Читатель", "Первый текст в Чтении"),
    ("grammar", "📚", "Грамотей", "Первая практика грамматики"),
    ("listening", "🎧", "Слушатель", "Первое аудирование"),
    ("video", "🎬", "Киноман", "Первое видео"),
    ("gamer", "🎮", "Геймер", "Сыграй в 3 разные игры"),
    ("rich", "🪙", "Богач", "Заработай 100 токенов"),
    ("magnate", "💎", "Магнат", "Заработай 500 токенов"),
]


def earned_achievements(db, user) -> list[dict]:
    reviews = db.query(LearningEvent).filter(LearningEvent.user_id == user.id).count()
    mods = {r.module for r in db.query(ConvSession)
            .filter(ConvSession.user_id == user.id).all()}
    games = sum(1 for m in mods if m.startswith("game_")) + (1 if "challenge" in mods else 0)
    streak = token_service.lesson_streak(db, user.id)
    earned_tokens = token_service.total_earned(db, user.id)

    cond = {
        "start": reviews >= 1,
        "rev100": reviews >= 100,
        "rev500": reviews >= 500,
        "streak7": streak >= 7,
        "lesson": "lesson_test" in mods,
        "speaking": "speaking" in mods,
        "writing": "writing" in mods,
        "reading": "reading" in mods,
        "grammar": "grammar" in mods,
        "listening": "listening" in mods,
        "video": "video" in mods,
        "gamer": games >= 3,
        "rich": earned_tokens >= 100,
        "magnate": earned_tokens >= 500,
    }
    return [{"icon": i, "title": t, "desc": d, "done": bool(cond.get(k))}
            for (k, i, t, d) in _DEFS]
