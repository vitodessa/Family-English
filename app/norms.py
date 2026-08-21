"""Дневные нормы по блокам урока — разные по уровню и нарастающие со временем.

Норма = базовое значение уровня × коэффициент роста. Коэффициент поднимается с
числом активных дней (за ~4 недели дорастает до +50%, затем плато). Смена уровня
даёт новую базу. Чтение и Аудирование масштабируются в своих сервисах по уровню.
"""
from app.config import CEFR_ORDER

# базовая дневная норма по уровню
BASE = {
    "A1": {"cards": 5, "grammar": 4, "test": 5, "write_words": 15, "speak_turns": 3},
    "A2": {"cards": 7, "grammar": 5, "test": 6, "write_words": 25, "speak_turns": 4},
    "B1": {"cards": 10, "grammar": 6, "test": 8, "write_words": 40, "speak_turns": 5},
    "B2": {"cards": 12, "grammar": 7, "test": 10, "write_words": 60, "speak_turns": 6},
    "C1": {"cards": 15, "grammar": 8, "test": 12, "write_words": 90, "speak_turns": 7},
    "C2": {"cards": 18, "grammar": 8, "test": 12, "write_words": 120, "speak_turns": 8},
}

RAMP_DAYS = 28      # за сколько активных дней норма дорастает до максимума
MAX_GROWTH = 0.5    # +50% на плато


def active_days(db, user_id: int) -> int:
    """Сколько разных дней ученик реально занимался (по журналу повторений)."""
    from app.models import LearningEvent
    rows = db.query(LearningEvent.reviewed_at).filter(LearningEvent.user_id == user_id).all()
    return len({r[0].date() for r in rows if r[0]})


def growth_factor(days: int) -> float:
    return 1.0 + MAX_GROWTH * min(days / RAMP_DAYS, 1.0)


def daily_norms(db, user) -> dict:
    """Дневные нормы блоков для ученика: база уровня × рост со временем."""
    lvl = (user.cefr_level or "A1").upper()
    base = BASE.get(lvl, BASE["A1"])
    g = growth_factor(active_days(db, user.id))
    return {k: max(1, round(v * g)) for k, v in base.items()}
