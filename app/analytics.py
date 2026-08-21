"""Аналитика реального обучения — из append-only лога и состояния колоды.

Показывает не «сколько наиграл», а что человек действительно усвоил:
удержание, слова в долгой памяти, регулярность, прогресс по уровням, слабые
места. Всё из данных (LearningEvent + Card + Session + Mistake), без API.
"""
from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import CEFR_ORDER
from app.models import Card, LearningEvent, Mistake, Session as ActSession, User, Word
from app.token_service import balance as token_balance

STATE_LABEL = {0: "Новые", 1: "Изучаются", 2: "В памяти", 3: "Повтор"}

MODULE_LABEL = {
    "study": "Карточки", "speaking": "Разговор", "reading": "Чтение",
    "writing": "Письмо", "listening": "Аудирование", "video": "Видео",
    "lesson": "Урок дня", "grammar": "Грамматика", "challenge": "Челлендж",
    "placement": "Срез знаний",
    "game_spell": "Игра: собери слово", "game_picture": "Игра: слово-картинка",
    "game_pairs": "Игра: пары", "game_memory": "Игра: мемори",
    "game_audio": "Игра: аудио", "game_anagram": "Игра: анаграмма",
    "game_hangman": "Игра: виселица", "game_missing": "Игра: буква",
    "game_speed": "Игра: на скорость", "challenge_win": "Челлендж",
}


def module_label(m):
    if m in MODULE_LABEL:
        return MODULE_LABEL[m]
    if m and m.startswith("game_"):
        return "Игра: " + m[5:]
    return m or "—"


def _streak(dates_set, today):
    """Длина серии подряд идущих дней с активностью, считая от сегодня/вчера."""
    d = today
    if today not in dates_set and (today - timedelta(days=1)) in dates_set:
        d = today - timedelta(days=1)
    n = 0
    while d in dates_set:
        n += 1
        d -= timedelta(days=1)
    return n


def user_analytics(db: Session, user: User) -> dict:
    uid = user.id
    now = datetime.utcnow()
    today = now.date()

    evs = db.query(LearningEvent).filter(LearningEvent.user_id == uid).all()
    total = len(evs)
    good = sum(1 for e in evs if e.rating >= 3)
    retention = round(good / total * 100) if total else 0

    cards = db.query(Card).filter(Card.user_id == uid).all()
    state_counts = Counter(c.state for c in cards)
    deck_states = [{"label": STATE_LABEL.get(s, str(s)), "count": state_counts.get(s, 0)}
                   for s in (0, 1, 2, 3)]
    learned = state_counts.get(2, 0)

    dates = {e.reviewed_at.date() for e in evs}
    streak = _streak(dates, today)
    active_days = len(dates)

    wk_ago = now - timedelta(days=7)
    reviews_7 = sum(1 for e in evs if e.reviewed_at >= wk_ago)

    # активность по дням за 30 дней
    day_counts = Counter(e.reviewed_at.date() for e in evs)
    activity = [{"date": today - timedelta(days=i),
                 "count": day_counts.get(today - timedelta(days=i), 0)}
                for i in range(29, -1, -1)]
    act_max = max((a["count"] for a in activity), default=0)

    # точность по неделям (8 недель)
    weeks = []
    for w in range(7, -1, -1):
        start = now - timedelta(days=(w + 1) * 7)
        end = now - timedelta(days=w * 7)
        wevs = [e for e in evs if start <= e.reviewed_at < end]
        wg = sum(1 for e in wevs if e.rating >= 3)
        weeks.append({"n": len(wevs), "acc": round(wg / len(wevs) * 100) if wevs else None})

    # прогресс по уровням (learned/total по уровню слова)
    word_ids = [c.word_id for c in cards if c.word_id]
    wl = {}
    if word_ids:
        for wid, lvl in db.query(Word.id, Word.cefr_level).filter(Word.id.in_(word_ids)).all():
            wl[wid] = lvl
    level_prog = []
    for lv in CEFR_ORDER:
        tot = sum(1 for c in cards if wl.get(c.word_id) == lv)
        lrn = sum(1 for c in cards if wl.get(c.word_id) == lv and c.state == 2)
        if tot:
            level_prog.append({"level": lv, "learned": lrn, "total": tot,
                               "pct": round(lrn / tot * 100)})

    # слабые слова: упорно заваливаемые (≥2 раза «Снова»); одна ошибка на новом — норма
    again = Counter(e.card_id for e in evs if e.rating == 1)
    cmap = {c.id: c for c in cards}
    weak = []
    for cid, n in again.most_common(20):
        if n < 2:
            break
        c = cmap.get(cid)
        if c:
            weak.append({"front": c.front, "back": c.back, "fails": n})
        if len(weak) >= 10:
            break

    # активность по модулям (единица — активные дни). Карточки Session не пишут —
    # берём их из дней с повторениями, чтобы главная активность была видна.
    mod_rows = (db.query(ActSession.module, func.count(ActSession.id))
                .filter(ActSession.user_id == uid).group_by(ActSession.module).all())
    # *_done — служебные отметки «зачёт блока», не показываем как активность
    modules = [{"label": module_label(m), "count": n}
               for m, n in mod_rows if not (m or "").endswith("_done")]
    if active_days:
        modules.append({"label": "Карточки", "count": active_days})
    modules.sort(key=lambda x: -x["count"])
    mod_max = max((m["count"] for m in modules), default=0)

    # ошибки по категориям (из разговора/письма)
    mist_rows = (db.query(Mistake.category, func.count(Mistake.id))
                 .filter(Mistake.user_id == uid).group_by(Mistake.category).all())
    mistakes = sorted(({"cat": c or "прочее", "count": n} for c, n in mist_rows),
                      key=lambda x: -x["count"])

    return {
        "user": user, "total_reviews": total, "retention": retention,
        "learned": learned, "cards_total": len(cards), "streak": streak,
        "active_days": active_days, "reviews_7": reviews_7,
        "deck_states": deck_states, "activity": activity, "act_max": act_max,
        "weeks": weeks, "level_prog": level_prog, "weak": weak,
        "modules": modules, "mod_max": mod_max, "mistakes": mistakes,
        "tokens": token_balance(db, uid),
    }


def family_overview(db: Session) -> list:
    """Сводка по всем ученикам для сравнения (без админов)."""
    rows = []
    for u in db.query(User).filter(User.is_admin == False).order_by(User.id).all():  # noqa: E712
        a = user_analytics(db, u)
        rows.append({
            "user": u, "learned": a["learned"], "retention": a["retention"],
            "reviews_7": a["reviews_7"], "streak": a["streak"],
            "total_reviews": a["total_reviews"], "tokens": a["tokens"],
        })
    return rows
