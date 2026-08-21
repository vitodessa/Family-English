"""Админка: обзор семьи, добавление учеников и слов."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.analytics import family_overview, user_analytics
from app.config import CEFR_ORDER, reporting_enabled
from app.database import get_db
from app.deps import get_current_user
from app.models import (
    Card, ChecklistCheck, ContentItem, LearningEvent, Mistake, TokenLedger, User, Word,
)
from app.models import Session as ConvSession
from app import token_service
from app.report_service import build_daily_report, send_telegram
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
                "tokens": token_service.balance(db, u.id),
                "tokens_month": token_service.earned_this_month(db, u.id),
            }
        )

    return render(
        request, "admin.html", db=db,
        rows=rows,
        levels=CEFR_ORDER,
        words_total=db.query(Word).count(),
        reporting=reporting_enabled(),
    )


@router.get("/admin/analytics")
def admin_analytics(request: Request, db: Session = Depends(get_db)):
    admin = _require_admin(request, db)
    if not admin:
        return RedirectResponse("/login", status_code=302)
    overview = family_overview(db)
    users = [user_analytics(db, u)
             for u in db.query(User).filter(User.is_admin == False).order_by(User.id).all()]  # noqa: E712
    return render(request, "admin_analytics.html", db=db,
                  overview=overview, users=users)


@router.post("/admin/send-report/{user_id}")
def send_report(user_id: int, request: Request, db: Session = Depends(get_db)):
    if not _require_admin(request, db):
        return RedirectResponse("/login", status_code=302)
    target = db.query(User).filter(User.id == user_id).first()
    if target:
        send_telegram(build_daily_report(db, target))  # ручная отправка, сразу
    return RedirectResponse("/admin", status_code=302)


@router.post("/admin/reset-password/{user_id}")
def reset_password(user_id: int, request: Request,
                   new_password: str = Form(...), db: Session = Depends(get_db)):
    """Сброс пароля ученику: админ задаёт новый пароль (пароли хешируются, старый не читается)."""
    if not _require_admin(request, db):
        return RedirectResponse("/login", status_code=302)
    target = db.query(User).filter(User.id == user_id).first()
    pw = (new_password or "").strip()
    if target and len(pw) >= 4:
        target.password_hash = hash_password(pw)
        db.commit()
    return RedirectResponse("/admin", status_code=303)


@router.post("/admin/delete-user/{user_id}")
def delete_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    """Удалить ученика со всеми его данными. Админа и себя удалить нельзя."""
    admin = _require_admin(request, db)
    if not admin:
        return RedirectResponse("/login", status_code=302)
    target = db.query(User).filter(User.id == user_id).first()
    if target and not target.is_admin and target.id != admin.id:
        for M in (ChecklistCheck, TokenLedger, Mistake, ConvSession, LearningEvent, Card):
            db.query(M).filter(M.user_id == target.id).delete()
        db.query(ContentItem).filter(ContentItem.created_by == target.id).delete()
        db.delete(target)
        db.commit()
    return RedirectResponse("/admin", status_code=303)


@router.post("/admin/cashout/{user_id}")
def cashout(user_id: int, request: Request, db: Session = Depends(get_db)):
    """Обмен токенов ученика на деньги: обнуляет баланс, пишет операцию в журнал."""
    if not _require_admin(request, db):
        return RedirectResponse("/login", status_code=302)
    token_service.cashout(db, user_id)
    return RedirectResponse("/admin", status_code=302)


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
