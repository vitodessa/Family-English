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

# Адаптивная нагрузка: чем больше занятий в день, тем тяжелее КАЖДОЕ занятие.
# См. правило [[unlimited-lessons-adaptive-load]] — занятий в день неограниченно.
INTENSITY_WINDOW = 7    # окно (дней) для оценки тенденции «занятий в день»
INTENSITY_STEP = 0.2    # +20% нагрузки за каждое доп. занятие/день сверх одного
INTENSITY_CAP = 2.0     # потолок множителя (одно занятие не станет неподъёмным)


def active_days(db, user_id: int) -> int:
    """Сколько разных дней ученик реально занимался (по журналу повторений)."""
    from app.models import LearningEvent
    rows = db.query(LearningEvent.reviewed_at).filter(LearningEvent.user_id == user_id).all()
    return len({r[0].date() for r in rows if r[0]})


def growth_factor(days: int) -> float:
    return 1.0 + MAX_GROWTH * min(days / RAMP_DAYS, 1.0)


def lessons_per_day(db, user_id: int, window_days: int = INTENSITY_WINDOW) -> float:
    """Среднее число завершённых занятий в день за последнее окно (тенденция)."""
    from datetime import datetime, timedelta
    from app.models import Session as ConvSession
    since = datetime.utcnow() - timedelta(days=window_days)
    n = (db.query(ConvSession)
         .filter(ConvSession.user_id == user_id,
                 ConvSession.module == "lesson_done",
                 ConvSession.started_at >= since)
         .count())
    return n / float(window_days)


def intensity_factor(db, user_id: int) -> float:
    """Множитель нагрузки по тенденции: 1.0 при ≤1 занятии/день, растёт до потолка."""
    avg = lessons_per_day(db, user_id)
    return min(INTENSITY_CAP, 1.0 + INTENSITY_STEP * max(0.0, avg - 1.0))


def daily_norms(db, user) -> dict:
    """Нормы блоков на ОДНО занятие: база уровня × рост со стажем × интенсивность.

    Занятий в день можно проходить сколько угодно; при устойчиво большом их числе
    нагрузка каждого занятия растёт пропорционально (см. intensity_factor).
    """
    lvl = (user.cefr_level or "A1").upper()
    base = BASE.get(lvl, BASE["A1"])
    g = growth_factor(active_days(db, user.id))
    f = intensity_factor(db, user.id)
    return {k: max(1, round(v * g * f)) for k, v in base.items()}
