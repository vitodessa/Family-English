"""Страница токенов ученика: баланс, серия, как заработать, история."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app import token_service
from app.database import get_db
from app.deps import get_current_user
from app.templating import render

router = APIRouter()


@router.get("/tokens")
def tokens_home(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    return render(request, "tokens.html", db=db,
                  balance=token_service.balance(db, user.id),
                  month=token_service.earned_this_month(db, user.id),
                  streak=token_service.lesson_streak(db, user.id),
                  history=token_service.recent(db, user.id))
