"""Лёгкая отметка активности модуля за день (через модель Session).

«Урок дня» вычисляет готовность шагов из этих отметок, не заводя отдельную
машину состояний. Идемпотентно: не больше одной записи на (пользователь, модуль, день).
"""

from datetime import datetime

from sqlalchemy.orm import Session as DBSession

from app.models import Session as ConvSession


def _day_start() -> datetime:
    d = datetime.utcnow().date()
    return datetime(d.year, d.month, d.day)


def touch_session(db: DBSession, user_id: int, module: str, summary: str = "") -> ConvSession:
    """Отметить, что ученик сегодня занимался этим модулем (одна запись на день)."""
    row = (db.query(ConvSession)
           .filter(ConvSession.user_id == user_id,
                   ConvSession.module == module,
                   ConvSession.started_at >= _day_start())
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
