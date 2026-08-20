"""Отчёт родителю: сводка по уроку дня + отправка в Telegram.

Отчёт собирается из уже накопленной активности (сессии, повторения, ошибки, тест).
Отправляется, когда урок пройден (все обязательные блоки) — один раз в день на ученика.
"""

from collections import Counter
from datetime import datetime

import httpx

from app.config import (
    LESSON_CARDS,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    reporting_enabled,
)
from app.models import LearningEvent, Mistake
from app.models import Session as ConvSession

_CAT_RU = {
    "grammar": "грамматика", "tense": "времена", "articles": "артикли",
    "prepositions": "предлоги", "word_order": "порядок слов", "vocab": "лексика",
    "pronunciation": "произношение", "spelling": "орфография",
    "punctuation": "пунктуация", "other": "прочее",
}


def _day_start() -> datetime:
    d = datetime.utcnow().date()
    return datetime(d.year, d.month, d.day)


def _modules_today(db, user_id: int) -> set[str]:
    return {r.module for r in db.query(ConvSession)
            .filter(ConvSession.user_id == user_id,
                    ConvSession.started_at >= _day_start()).all()}


def _reviews_today(db, user_id: int) -> tuple[int, int]:
    q = db.query(LearningEvent).filter(LearningEvent.user_id == user_id,
                                       LearningEvent.reviewed_at >= _day_start())
    total = q.count()
    good = q.filter(LearningEvent.rating >= 3).count()
    return total, good


def lesson_complete(db, user_id: int) -> bool:
    """Пройдены ли все обязательные блоки урока (кроме разговора) + тест."""
    mods = _modules_today(db, user_id)
    reviews, _ = _reviews_today(db, user_id)
    return (reviews >= LESSON_CARDS
            and {"grammar", "reading", "writing", "lesson_test"} <= mods)


def build_daily_report(db, user) -> str:
    ds = _day_start()
    mods = _modules_today(db, user.id)
    reviews, good = _reviews_today(db, user.id)
    pct = round(good / reviews * 100) if reviews else 0

    mistakes = (db.query(Mistake)
                .filter(Mistake.user_id == user.id, Mistake.created_at >= ds).all())
    cats = Counter((m.category or "other") for m in mistakes)
    top = ", ".join(f"{_CAT_RU.get(c, c)} ({n})" for c, n in cats.most_common(3))

    test = (db.query(ConvSession)
            .filter(ConvSession.user_id == user.id, ConvSession.module == "lesson_test",
                    ConvSession.started_at >= ds).first())

    def mark(cond):
        return "✅" if cond else "⬜️"

    lines = [
        f"📚 <b>Урок дня — {user.name}</b> ({datetime.utcnow():%d.%m})",
        "",
        f"{mark(reviews >= LESSON_CARDS)} Карточки — повторений: {reviews}"
        + (f" (верно {pct}%)" if reviews else ""),
        f"{mark('grammar' in mods)} Грамматика",
        f"{mark('reading' in mods)} Чтение",
        f"{mark('writing' in mods)} Письмо",
        f"{mark('speaking' in mods)} Разговор",
        f"{mark(test is not None)} Финальный тест"
        + (f" — {test.summary}" if test and test.summary else ""),
    ]
    if mistakes:
        lines += ["", f"✍️ Ошибок сегодня: {len(mistakes)}" + (f" · {top}" if top else "")]
    return "\n".join(lines)


def send_telegram(text: str) -> bool:
    if not reporting_enabled():
        return False
    try:
        r = httpx.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=15,
        )
        return r.status_code == 200
    except Exception:  # noqa: BLE001
        return False


def maybe_send_report(db, user) -> bool:
    """Отправить отчёт, если урок пройден и сегодня ещё не отправляли."""
    if not reporting_enabled() or not lesson_complete(db, user.id):
        return False
    ds = _day_start()
    already = (db.query(ConvSession)
               .filter(ConvSession.user_id == user.id, ConvSession.module == "report_sent",
                       ConvSession.started_at >= ds).first())
    if already:
        return False
    if send_telegram(build_daily_report(db, user)):
        db.add(ConvSession(user_id=user.id, module="report_sent", summary="ok"))
        db.commit()
        return True
    return False
