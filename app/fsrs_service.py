"""Обёртка над настоящим планировщиком FSRS (пакет fsrs).

Здесь вся «наука» интервального повторения. Состояние карточки храним как
JSON-словарь, datetime сериализуем в ISO-строку, чтобы класть в БД.
"""

import json
from datetime import datetime, timezone
from typing import Optional

from fsrs import FSRS, Card, Rating

_scheduler = FSRS()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_jsonable(d: dict) -> dict:
    d = dict(d)
    due = d.get("due")
    if isinstance(due, datetime):
        d["due"] = due.isoformat()
    return d


def _load(state: dict) -> Card:
    # Card.from_dict сам разбирает due из ISO-строки, поэтому строку не трогаем,
    # а datetime (если вдруг прилетит) приводим к ISO-строке.
    d = dict(state)
    due = d.get("due")
    if isinstance(due, datetime):
        d["due"] = due.isoformat()
    return Card.from_dict(d)


def _as_naive_utc(dt: datetime) -> datetime:
    """Приводим к наивному UTC — так удобно сравнивать в SQLite."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def new_card_state(now: Optional[datetime] = None) -> tuple[str, datetime]:
    """Создать стартовое состояние карточки. Возвращает (fsrs_json, due_naive)."""
    now = now or _now()
    card = Card()
    card.due = now
    state = _to_jsonable(card.to_dict())
    return json.dumps(state), _as_naive_utc(card.due)


def apply_review(fsrs_json: str, rating: int, now: Optional[datetime] = None) -> dict:
    """Применить оценку (1..4) к карточке. Возвращает новое состояние и метаданные."""
    now = now or _now()
    card = _load(json.loads(fsrs_json))
    scheduling = _scheduler.repeat(card, now)
    info = scheduling[Rating(rating)]
    new_card = info.card
    log = info.review_log
    return {
        "fsrs_json": json.dumps(_to_jsonable(new_card.to_dict())),
        "due": _as_naive_utc(new_card.due),
        "state": new_card.state.value,
        "reps": new_card.reps,
        "elapsed_days": log.elapsed_days,
        "scheduled_days": log.scheduled_days,
    }
