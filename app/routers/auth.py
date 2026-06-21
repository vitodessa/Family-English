"""Регистрация, вход, выход. Пароли хэшируются, сессия в подписанной cookie."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import CEFR_ORDER
from app.database import get_db
from app.models import User
from app.security import hash_password, verify_password
from app.seed import generate_cards_for_user
from app.templating import render

router = APIRouter()


@router.get("/register")
def register_page(request: Request, db: Session = Depends(get_db)):
    return render(request, "register.html", db=db, levels=CEFR_ORDER)


@router.post("/register")
def register(
    request: Request,
    name: str = Form(...),
    password: str = Form(...),
    cefr_level: str = Form("A1"),
    db: Session = Depends(get_db),
):
    name = name.strip()
    if not name or not password:
        return render(request, "register.html", db=db, levels=CEFR_ORDER,
                      error="Имя и пароль обязательны")

    if db.query(User).filter(User.name == name).first():
        return render(request, "register.html", db=db, levels=CEFR_ORDER,
                      error="Такое имя уже занято")

    user = User(
        name=name,
        password_hash=hash_password(password),
        cefr_level=cefr_level if cefr_level in CEFR_ORDER else "A1",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    generate_cards_for_user(db, user)

    request.session["user_id"] = user.id
    return RedirectResponse("/dashboard", status_code=302)


@router.get("/login")
def login_page(request: Request, db: Session = Depends(get_db)):
    return render(request, "login.html", db=db)


@router.post("/login")
def login(
    request: Request,
    name: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.name == name.strip()).first()
    if not user or not verify_password(password, user.password_hash):
        return render(request, "login.html", db=db, error="Неверное имя или пароль")

    request.session["user_id"] = user.id
    return RedirectResponse("/dashboard", status_code=302)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=302)
