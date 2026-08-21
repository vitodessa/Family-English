"""Отчёт родителю: сводка по уроку дня + отправка в Telegram.

Отчёт собирается из уже накопленной активности (сессии, повторения, ошибки, тест).
Отправляется, когда урок пройден (все обязательные блоки) — один раз в день на ученика.
"""

from collections import Counter
from datetime import datetime, timedelta

import httpx

from app.config import (
    CEFR_ORDER,
    LESSON_CARDS,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    listening_enabled,
    reporting_enabled,
    speaking_enabled,
)
from app.models import ContentItem, LearningEvent, Mistake, User
from app.models import Session as ConvSession
from app.norms import daily_norms

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
    return _reviews_since(db, user_id, _day_start())


def _reviews_since(db, user_id: int, since: datetime) -> tuple[int, int]:
    q = db.query(LearningEvent).filter(LearningEvent.user_id == user_id,
                                       LearningEvent.reviewed_at >= since)
    total = q.count()
    good = q.filter(LearningEvent.rating >= 3).count()
    return total, good


def _students(db):
    return db.query(User).filter(User.is_admin == False).order_by(User.id).all()  # noqa: E712


def _allowed_levels(user):
    try:
        idx = CEFR_ORDER.index((user.cefr_level or "A1").upper())
    except ValueError:
        idx = 0
    return CEFR_ORDER[:idx + 1]


def _has_video(db, user) -> bool:
    return (db.query(ContentItem)
            .filter(ContentItem.kind == "video",
                    ContentItem.cefr_level.in_(_allowed_levels(user))).first()) is not None


def required_modules(db, user) -> set:
    """Обязательные блоки урока дня (те же, что показывает /lesson).

    Аудирование/Разговор — если модуль включён; Видео — если для уровня есть ролик.
    """
    mods = {"grammar", "reading", "writing_done", "lesson_test"}
    if listening_enabled():
        mods.add("listening")
    if speaking_enabled():
        mods.add("speaking_done")
    if _has_video(db, user):
        mods.add("video")
    return mods


def lesson_complete(db, user_id: int) -> bool:
    """Пройдены ли ВСЕ обязательные блоки урока (включая аудирование и разговор) + тест."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return False
    mods = _modules_today(db, user_id)
    reviews, _ = _reviews_today(db, user_id)
    played_game = any(m.startswith("game_") for m in mods)
    return (reviews >= daily_norms(db, user)["cards"]
            and required_modules(db, user) <= mods
            and played_game)


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

    n = daily_norms(db, user)
    lines = [
        f"📚 <b>Урок дня — {user.name}</b> ({datetime.utcnow():%d.%m})",
        "",
        f"{mark(reviews >= n['cards'])} Карточки — повторений: {reviews}/{n['cards']}"
        + (f" (верно {pct}%)" if reviews else ""),
        f"{mark('grammar' in mods)} Грамматика",
        f"{mark('reading' in mods)} Чтение",
    ]
    if listening_enabled():
        lines.append(f"{mark('listening' in mods)} Аудирование")
    lines.append(f"{mark('writing_done' in mods)} Письмо")
    if speaking_enabled():
        lines.append(f"{mark('speaking_done' in mods)} Разговор")
    lines.append(f"{mark(any(m.startswith('game_') for m in mods))} Игры")
    if _has_video(db, user):
        lines.append(f"{mark('video' in mods)} Видео")
    lines.append(f"{mark(test is not None)} Финальный тест"
                 + (f" — {test.summary}" if test and test.summary else ""))
    if mistakes:
        lines += ["", f"✍️ Ошибок сегодня: {len(mistakes)}" + (f" · {top}" if top else "")]

    # обогащение из аналитики: серия, слова в памяти, западающие слова
    from app.analytics import user_analytics
    a = user_analytics(db, user)
    lines += ["", f"🔥 Серия: {a['streak']} дн.  ·  🧠 в памяти: {a['learned']} слов"]
    if a["weak"]:
        lines += ["⚠️ Западают: " + ", ".join(w["front"] for w in a["weak"][:2])]
    return "\n".join(lines)


def build_evening_status(db) -> str:
    """Вечерний срез по всей семье: кто прошёл урок, кто занимался, кто нет."""
    lines = [f"🌙 <b>Итоги дня</b> ({datetime.utcnow():%d.%m})", ""]
    for u in _students(db):
        reviews, good = _reviews_today(db, u.id)
        if lesson_complete(db, u.id):
            pct = round(good / reviews * 100) if reviews else 0
            lines.append(f"✅ {u.name} — урок пройден ({reviews} повт., верно {pct}%)")
        elif reviews > 0:
            lines.append(f"🔸 {u.name} — занимался, урок не завершён ({reviews} повт.)")
        else:
            lines.append(f"⬜️ {u.name} — сегодня не занимался")
    return "\n".join(lines)


def build_weekly_digest(db) -> str:
    """Итоги недели по каждому ученику — из накопленной аналитики."""
    from app.analytics import user_analytics
    since = datetime.utcnow() - timedelta(days=7)
    lines = [f"📅 <b>Итоги недели</b> ({datetime.utcnow():%d.%m})"]
    for u in _students(db):
        tot, good = _reviews_since(db, u.id, since)
        pct = round(good / tot * 100) if tot else 0
        a = user_analytics(db, u)
        lines += ["", f"👤 <b>{u.name}</b> · {u.cefr_level}"]
        lines.append("   Повторений за неделю: "
                     + (f"{tot} (верно {pct}%)" if tot else "0 — не занимался"))
        lines.append(f"   🧠 в памяти: {a['learned']} слов  ·  🔥 серия {a['streak']} дн.")
        if a["weak"]:
            lines.append("   ⚠️ западают: " + ", ".join(w["front"] for w in a["weak"][:3]))
    return "\n".join(lines)


def run_evening(db) -> bool:
    """Плановое: вечерний статус семьи (в т.ч. «не занимался»)."""
    if not reporting_enabled():
        return False
    return send_telegram(build_evening_status(db))


def run_weekly(db) -> bool:
    """Плановое: недельный дайджест."""
    if not reporting_enabled():
        return False
    return send_telegram(build_weekly_digest(db))


def build_morning_reminder(db) -> str:
    """Утренний пинок: кто ещё не сделал урок сегодня + серии (чтоб было что терять)."""
    from app.analytics import user_analytics
    lines = ["🌅 <b>Пора на урок английского!</b>", ""]
    pending, streaks = [], []
    for u in _students(db):
        if not lesson_complete(db, u.id):
            pending.append(u.name)
        a = user_analytics(db, u)
        if a["streak"] > 0:
            streaks.append("%s %d" % (u.name, a["streak"]))
    if pending:
        lines.append("Сегодня ещё не занимались: <b>" + ", ".join(pending) + "</b>")
        lines.append("Один «Начать урок» — и готово.")
    else:
        lines.append("Все уже позанимались сегодня — красота 🎉")
    if streaks:
        lines += ["", "🔥 Серии: " + " · ".join(streaks) + " — не растеряйте!"]
    return "\n".join(lines)


def run_morning(db) -> bool:
    """Плановое: утреннее напоминание."""
    if not reporting_enabled():
        return False
    return send_telegram(build_morning_reminder(db))


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
