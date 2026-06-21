"""Ввод слов учеником из уроков EnglishDom (массовая вставка)."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Card
from app.seed import add_words_for_user
from app.templating import render

router = APIRouter()


@router.get("/my-words")
def my_words_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    total = db.query(Card).filter(Card.user_id == user.id).count()
    return render(request, "my_words.html", db=db, total=total)


@router.post("/my-words")
def my_words_add(
    request: Request,
    words: str = Form(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    added = add_words_for_user(db, user, words)
    total = db.query(Card).filter(Card.user_id == user.id).count()
    return render(
        request, "my_words.html", db=db, total=total,
        added=added,
    )
