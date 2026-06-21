"""Админка: обзор семьи, добавление учеников и слов."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import CEFR_ORDER
from app.database import get_db
from app.deps import get_current_user
from app.models import Card, LearningEvent, User, Word
from app.security import hash_password
from app.seed import generate_cards_for_user, seed_words
from app.templating import render

router = APIRouter()


def _require_admin(request: Request, db: Session):
    user = get_current_user(request, db)
    if not user or not user.is_admin:
        return None
    return user


@router.get("/admin")
def admin_page(request: Request, db: Session = Depends(get_db)):
    admin = _require_admin(request, db)
    if not admin:
        return RedirectResponse("/login", status_code=302)

    rows = []
    for u in db.query(User).order_by(User.id).all():
        rows.append(
            {
                "user": u,
                "cards": db.query(Card).filter(Card.user_id == u.id).count(),
                "reviews": db.query(LearningEvent)
                .filter(LearningEvent.user_id == u.id)
                .count(),
            }
        )

    return render(
        request, "admin.html", db=db,
        rows=rows,
        levels=CEFR_ORDER,
        words_total=db.query(Word).count(),
    )


@router.post("/admin/add-user")
def add_user(
    request: Request,
    name: str = Form(...),
    password: str = Form(...),
    cefr_level: str = Form("A1"),
    db: Session = Depends(get_db),
):
    if not _require_admin(request, db):
        return RedirectResponse("/login", status_code=302)

    name = name.strip()
    if name and password and not db.query(User).filter(User.name == name).first():
        user = User(
            name=name,
            password_hash=hash_password(password),
            cefr_level=cefr_level if cefr_level in CEFR_ORDER else "A1",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        generate_cards_for_user(db, user)

    return RedirectResponse("/admin", status_code=302)


@router.post("/admin/add-word")
def add_word(
    request: Request,
    front: str = Form(...),
    back: str = Form(...),
    cefr_level: str = Form("A1"),
    db: Session = Depends(get_db),
):
    if not _require_admin(request, db):
        return RedirectResponse("/login", status_code=302)

    front, back = front.strip(), back.strip()
    if front and back:
        exists = (
            db.query(Word)
            .filter(Word.front == front, Word.cefr_level == cefr_level)
            .first()
        )
        if not exists:
            db.add(Word(front=front, back=back, cefr_level=cefr_level))
            db.commit()

    return RedirectResponse("/admin", status_code=302)


@router.post("/admin/seed-words")
def reseed(request: Request, db: Session = Depends(get_db)):
    if not _require_admin(request, db):
        return RedirectResponse("/login", status_code=302)
    seed_words(db)
    return RedirectResponse("/admin", status_code=302)
