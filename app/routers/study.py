"""Дашборд ученика и режим учёбы (карточки на FSRS)."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.fsrs_service import apply_review
from app.models import Card, LearningEvent
from app.templating import render

router = APIRouter()


def _due_query(db: Session, user_id: int):
    now = datetime.utcnow()
    return (
        db.query(Card)
        .filter(Card.user_id == user_id, Card.due <= now)
        .order_by(Card.due.asc())
    )


@router.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

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

    return render(
        request, "dashboard.html", db=db,
        total_cards=total_cards,
        due_count=due_count,
        learned=learned,
        retention=retention,
        reviews_today=reviews_today,
        daily_goal=goal,
        goal_progress=goal_progress,
    )


@router.get("/study")
def study(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    card = _due_query(db, user.id).first()
    due_count = _due_query(db, user.id).count()
    return render(request, "study.html", db=db, card=card, due_count=due_count)


@router.post("/review")
def review(
    request: Request,
    card_id: int = Form(...),
    rating: int = Form(...),
    db: Session = Depends(get_db),
):
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

    result = apply_review(card.fsrs_json, rating)
    card.fsrs_json = result["fsrs_json"]
    card.due = result["due"]
    card.state = result["state"]
    card.reps = result["reps"]

    # append-only журнал: запись о повторении, без правок задним числом
    db.add(
        LearningEvent(
            user_id=user.id,
            card_id=card.id,
            grammar_topic_id=card.grammar_topic_id,  # тег грамматики для сквозного слоя
            rating=rating,
            state_after=result["state"],
            elapsed_days=result["elapsed_days"],
            scheduled_days=result["scheduled_days"],
        )
    )
    db.commit()

    return RedirectResponse("/study", status_code=302)
