"""Токен-экономика: дети зарабатывают токены за учёбу, родитель раз в месяц меняет на деньги.

Журнал append-only (TokenLedger). Награды идемпотентны за день (once_key).
"""

from datetime import datetime, timedelta

from sqlalchemy import func

from app.models import TokenLedger

LESSON_TOKENS = 25
GAME_TOKENS = 3
CHALLENGE_WIN_TOKENS = 5
STREAK_CAP = 10  # бонус за серию не больше этого

_LESSON_REASON = "Урок дня"


def _day_start() -> datetime:
    d = datetime.utcnow().date()
    return datetime(d.year, d.month, d.day)


def _today_key() -> str:
    return datetime.utcnow().date().isoformat()


def balance(db, user_id: int) -> int:
    return int(db.query(func.coalesce(func.sum(TokenLedger.amount), 0))
               .filter(TokenLedger.user_id == user_id).scalar() or 0)


def total_earned(db, user_id: int) -> int:
    return int(db.query(func.coalesce(func.sum(TokenLedger.amount), 0))
               .filter(TokenLedger.user_id == user_id, TokenLedger.amount > 0).scalar() or 0)


def earned_this_month(db, user_id: int) -> int:
    d = datetime.utcnow()
    start = datetime(d.year, d.month, 1)
    return int(db.query(func.coalesce(func.sum(TokenLedger.amount), 0))
               .filter(TokenLedger.user_id == user_id, TokenLedger.amount > 0,
                       TokenLedger.created_at >= start).scalar() or 0)


def award(db, user_id: int, amount: int, reason: str, once_key=None) -> int:
    """Начислить токены. Если once_key задан и уже начислялось сегодня — 0."""
    if once_key:
        exists = (db.query(TokenLedger)
                  .filter(TokenLedger.user_id == user_id, TokenLedger.once_key == once_key,
                          TokenLedger.created_at >= _day_start()).first())
        if exists:
            return 0
    db.add(TokenLedger(user_id=user_id, amount=amount, reason=reason, once_key=once_key))
    db.commit()
    return amount


def lesson_streak(db, user_id: int) -> int:
    """Сколько дней подряд (включая сегодня/вчера) пройден урок дня."""
    rows = (db.query(TokenLedger.created_at)
            .filter(TokenLedger.user_id == user_id, TokenLedger.reason == _LESSON_REASON)
            .all())
    days = sorted({r[0].date() for r in rows}, reverse=True)
    if not days:
        return 0
    today = datetime.utcnow().date()
    if days[0] not in (today, today - timedelta(days=1)):
        return 0
    streak, expect = 0, days[0]
    for d in days:
        if d == expect:
            streak += 1
            expect = expect - timedelta(days=1)
        else:
            break
    return streak


def award_lesson(db, user_id: int) -> int:
    """Начислить за пройденный урок + бонус за серию (один раз в день)."""
    got = award(db, user_id, LESSON_TOKENS, _LESSON_REASON, once_key=f"lesson:{_today_key()}")
    if not got:
        return 0
    streak = lesson_streak(db, user_id)  # уже включает сегодня
    bonus = min(streak, STREAK_CAP)
    if bonus:
        got += award(db, user_id, bonus, f"Серия {streak} дн.", once_key=f"streak:{_today_key()}")
    return got


def award_game(db, user_id: int, game: str, win: bool = False) -> int:
    """Начислить за игру (один раз в день на игру); +бонус за победу в челлендже."""
    got = award(db, user_id, GAME_TOKENS, "Игра", once_key=f"game_{game}:{_today_key()}")
    if game == "challenge" and win:
        got += award(db, user_id, CHALLENGE_WIN_TOKENS, "Победа в челлендже",
                     once_key=f"challenge_win:{_today_key()}")
    return got


def cashout(db, user_id: int) -> int:
    """Обмен: обнулить баланс, записав отрицательную операцию. Возвращает обменянную сумму."""
    bal = balance(db, user_id)
    if bal <= 0:
        return 0
    db.add(TokenLedger(user_id=user_id, amount=-bal, reason="Обмен на деньги"))
    db.commit()
    return bal


def recent(db, user_id: int, limit: int = 15):
    return (db.query(TokenLedger).filter(TokenLedger.user_id == user_id)
            .order_by(TokenLedger.created_at.desc()).limit(limit).all())
