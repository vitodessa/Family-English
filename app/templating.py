"""Единая точка рендеринга шаблонов с общим контекстом (текущий пользователь)."""

from typing import Optional

from fastapi import Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import APP_TITLE, BASE_DIR
from app.deps import get_current_user

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


def render(request: Request, name: str, db: Optional[Session] = None, **context):
    current_user = get_current_user(request, db) if db is not None else None
    base = {
        "request": request,
        "app_title": APP_TITLE,
        "current_user": current_user,
    }
    base.update(context)
    return templates.TemplateResponse(name, base)
