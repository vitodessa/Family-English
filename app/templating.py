"""Единая точка рендеринга шаблонов с общим контекстом (текущий пользователь)."""

import hashlib
from typing import Optional

from fastapi import Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import APP_TITLE, BASE_DIR
from app.deps import get_current_user

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


def _asset_version() -> str:
    """Короткий хеш style.css — метка версии для сброса кэша браузера.

    Меняется только при изменении стилей; в ссылке ?v=<hash> заставляет браузер
    скачать свежий CSS после деплоя, а не держать старый из кэша.
    """
    try:
        data = (BASE_DIR / "app" / "static" / "style.css").read_bytes()
        return hashlib.md5(data).hexdigest()[:8]
    except Exception:  # noqa: BLE001
        return "0"


ASSET_VERSION = _asset_version()


def render(request: Request, name: str, db: Optional[Session] = None, **context):
    current_user = get_current_user(request, db) if db is not None else None
    base = {
        "request": request,
        "app_title": APP_TITLE,
        "current_user": current_user,
        "asset_version": ASSET_VERSION,
    }
    base.update(context)
    return templates.TemplateResponse(name, base)
