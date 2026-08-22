"""Отметка активности модуля в рамках ТЕКУЩЕГО занятия (через модель Session).

«Урок дня» вычисляет готовность шагов из этих отметок. Занятий в день может быть
сколько угодно: отметки считаются в рамках круга (round), а не всего дня —
после завершения урока (`record_lesson_done`) круг начинается заново, и все
блоки нужно пройти снова для следующего занятия. См. [[unlimited-lessons-adaptive-load]].
"""

from datetime import datetime

from sqlalchemy.orm import Session as DBSession

from app.models import Session as ConvSession

LESSON_DONE = "lesson_done"   # маркер завершённого занятия (граница круга)


def _day_start() -> datetime:
    d = datetime.utcnow().date()
    return datetime(d.year, d.month, d.day)


def round_start(db: DBSession, user_id: int) -> datetime:
    """Начало текущего занятия: время последнего завершённого урока сегодня, иначе начало дня.

    До первого завершения (и до внедрения фичи) равно началу дня — поведение как раньше.
    """
    ds = _day_start()
    last = (db.query(ConvSession)
            .filter(ConvSession.user_id == user_id,
                    ConvSession.module == LESSON_DONE,
                    ConvSession.started_at >= ds)
            .order_by(ConvSession.started_at.desc())
            .first())
    return last.started_at if last else ds


def lessons_today(db: DBSession, user_id: int) -> int:
    """Сколько занятий завершено сегодня."""
    return (db.query(ConvSession)
            .filter(ConvSession.user_id == user_id,
                    ConvSession.module == LESSON_DONE,
                    ConvSession.started_at >= _day_start())
            .count())


def touch_session(db: DBSession, user_id: int, module: str, summary: str = "") -> ConvSession:
    """Отметить, что ученик занимался этим модулем в ТЕКУЩЕМ занятии (одна запись на круг)."""
    rs = round_start(db, user_id)
    row = (db.query(ConvSession)
           .filter(ConvSession.user_id == user_id,
                   ConvSession.module == module,
                   ConvSession.started_at >= rs)
           .first())
    if row:
        if summary:
            row.summary = summary
            db.commit()
        return row
    row = ConvSession(user_id=user_id, module=module, summary=summary)
    db.add(row)
    db.commit()
    return row


def record_lesson_done(db: DBSession, user_id: int, summary: str = "Урок завершён") -> ConvSession:
    """Отметить завершение урока: закрывает круг и увеличивает счётчик занятий за день."""
    row = ConvSession(user_id=user_id, module=LESSON_DONE, summary=summary)
    db.add(row)
    db.commit()
    return row
