"""Дашборд ученика и режим учёбы (карточки на FSRS).

Учёба — активное припоминание: показываем слово в одну сторону, ученик выбирает
правильный вариант из нескольких. Автопроверка превращается в оценку FSRS
(верно → «Хорошо», ошибка → «Снова») — методология интервалов не меняется.
"""

import random
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.emoji_map import emoji_for
from app.fsrs_service import apply_review
from app.models import Card, LearningEvent, User, Word
from app.seed import top_up_deck
from app.templating import render
from app.token_service import balance as token_balance

router = APIRouter()

QUIZ_OPTIONS = 3  # всего вариантов в вопросе (1 верный + обманки)


def _due_query(db: Session, user_id: int):
    now = datetime.utcnow()
    return (
        db.query(Card)
        .filter(Card.user_id == user_id, Card.due <= now)
        .order_by(Card.due.asc())
    )


def _distractors(db: Session, column, correct: str, level, need: int) -> list[str]:
    """Правдоподобные неверные варианты: другие слова того же уровня (при нехватке — любые)."""
    seen = {(correct or "").strip().lower()}
    out: list[str] = []

    def _collect(rows):
        for row in rows:
            val = row[0]
            key = (val or "").strip().lower()
            if key and key not in seen:
                seen.add(key)
                out.append(val)
            if len(out) >= need:
                return

    base = db.query(column).filter(column != correct)
    if level:
        _collect(base.filter(Word.cefr_level == level).order_by(func.random()).limit(40).all())
    if len(out) < need:  # уровень дал мало — добираем из всего каталога
        _collect(base.order_by(func.random()).limit(40).all())
    return out


def _make_quiz(db: Session, card: Card) -> dict:
    """Собрать вопрос по карточке: случайное направление + перемешанные варианты."""
    direction = random.choice(["ru2en", "en2ru"])
    word = db.query(Word).filter(Word.id == card.word_id).first() if card.word_id else None
    level = word.cefr_level if word else None

    if direction == "ru2en":
        prompt, correct, column = card.back, card.front, Word.front
        hint = "Как это по-английски?"
    else:
        prompt, correct, column = card.front, card.back, Word.back
        hint = "Что это значит?"

    options = _distractors(db, column, correct, level, QUIZ_OPTIONS - 1) + [correct]
    random.shuffle(options)
    return {
        "direction": direction,
        "prompt": prompt,
        "correct": correct,
        "options": options,
        "hint": hint,
        "en_word": card.front,       # для озвучки английского слова
        "emoji": emoji_for(card.front),  # «картинка» слова, если есть
    }


def _grade(db: Session, user, card: Card, rating: int) -> None:
    """Применить оценку к карточке (FSRS) и записать событие в журнал (append-only)."""
    result = apply_review(card.fsrs_json, rating)
    card.fsrs_json = result["fsrs_json"]
    card.due = result["due"]
    card.state = result["state"]
    card.reps = result["reps"]
    db.add(LearningEvent(
        user_id=user.id,
        card_id=card.id,
        grammar_topic_id=card.grammar_topic_id,  # тег грамматики для сквозного слоя
        rating=rating,
        state_after=result["state"],
        elapsed_days=result["elapsed_days"],
        scheduled_days=result["scheduled_days"],
    ))
    db.commit()


@router.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    top_up_deck(db, user)  # долив свежих слов по мере изучения

    today = datetime.utcnow().date()
    total_cards = db.query(Card).filter(Card.user_id == user.id).count()
    due_count = _due_query(db, user.id).count()
    learned = (
        db.query(Card)
        .filter(Card.user_id == user.id, Card.state == 2)
        .count()
    )

    all_events = db.query(LearningEvent).filter(LearningEvent.user_id == user.id)
    total_reviews = all_events.count()
    good_reviews = all_events.filter(LearningEvent.rating >= 3).count()
    retention = round(good_reviews / total_reviews * 100) if total_reviews else 0

    reviews_today = (
        db.query(LearningEvent)
        .filter(
            LearningEvent.user_id == user.id,
            LearningEvent.reviewed_at >= datetime(today.year, today.month, today.day),
        )
        .count()
    )
    goal = user.daily_goal or 0
    goal_progress = min(round(reviews_today / goal * 100), 100) if goal else 0

    # Таблица лидеров семьи по токенам (соревновательный элемент).
    leaderboard = sorted(
        [{"name": u.name, "tokens": token_balance(db, u.id), "me": u.id == user.id}
         for u in db.query(User).all()],
        key=lambda p: -p["tokens"],
    )

    return render(
        request, "dashboard.html", db=db,
        leaderboard=leaderboard,
        total_cards=total_cards,
        due_count=due_count,
        learned=learned,
        retention=retention,
        reviews_today=reviews_today,
        daily_goal=goal,
        goal_progress=goal_progress,
        tokens=token_balance(db, user.id),
    )


@router.get("/study")
def study(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    top_up_deck(db, user)  # долив свежих слов по мере изучения

    card = _due_query(db, user.id).first()
    due_count = _due_query(db, user.id).count()
    quiz = _make_quiz(db, card) if card else None
    return render(request, "study.html", db=db, card=card, due_count=due_count, quiz=quiz)


@router.post("/study/answer")
def study_answer(
    request: Request,
    card_id: int = Form(...),
    direction: str = Form(...),
    chosen: str = Form(""),
    db: Session = Depends(get_db),
):
    """Ответ на вопрос: сверяем выбор с правильным и превращаем в оценку FSRS."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    card = (
        db.query(Card)
        .filter(Card.id == card_id, Card.user_id == user.id)  # только свои карточки
        .first()
    )
    if not card:
        return RedirectResponse("/study", status_code=302)

    correct = card.front if direction == "ru2en" else card.back
    ok = chosen.strip().lower() == (correct or "").strip().lower()
    _grade(db, user, card, rating=3 if ok else 1)  # верно → «Хорошо», ошибка → «Снова»
    return RedirectResponse("/study", status_code=302)


@router.post("/review")
def review(
    request: Request,
    card_id: int = Form(...),
    rating: int = Form(...),
    db: Session = Depends(get_db),
):
    """Ручная оценка (совместимость / дымовой тест). Основной путь — /study/answer."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    card = (
        db.query(Card)
        .filter(Card.id == card_id, Card.user_id == user.id)  # только свои карточки
        .first()
    )
    if not card or rating not in (1, 2, 3, 4):
        return RedirectResponse("/study", status_code=302)

    _grade(db, user, card, rating)
    return RedirectResponse("/study", status_code=302)
