"""Определение текущего пользователя по сессии (подписанная cookie)."""

from typing import Optional

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import User


def get_current_user(request: Request, db: Session) -> Optional[User]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id).first()
