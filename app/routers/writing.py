"""Письмо: задание под уровень → ученик пишет → разбор (исправление + ошибки + слова).

Разбор пишется в «единую память»: ошибки → Mistake (source_module="writing", видны
в «Разборе речи»), новые слова → карточки. Сессия логируется.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session as DBSession

from app import speaking_service, writing_service
from app.config import writing_enabled
from app.database import get_db
from app.deps import get_current_user
from app.models import Session as ConvSession
from app.templating import render

router = APIRouter()


@router.get("/writing")
def writing_home(request: Request, db: DBSession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    task = writing_service.get_task(user.cefr_level or "A1") if writing_enabled() else ""
    return render(request, "writing.html", db=db, task=task, enabled=writing_enabled())


@router.post("/writing/review")
def writing_review(
    request: Request,
    task: str = Form(...),
    text: str = Form(...),
    db: DBSession = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if not writing_enabled():
        return RedirectResponse("/writing", status_code=302)

    text = (text or "").strip()
    if not text:
        return RedirectResponse("/writing", status_code=302)

    level = (user.cefr_level or "A1").upper()
    try:
        parsed = writing_service.review(user, level, task, text)
    except Exception as e:  # noqa: BLE001 — покажем ошибку на странице
        return render(request, "writing.html", db=db, task=task,
                      enabled=True, error=f"Не удалось разобрать: {e}", draft=text)

    # Сессия + сохранение в единую память (ошибки и слова)
    conv = ConvSession(user_id=user.id, module="writing", topic=task[:200])
    db.add(conv)
    db.commit()
    db.refresh(conv)
    speaking_service._save_turn(db, user, conv.id, parsed, source_module="writing")
    conv.summary = ("Письмо: " + (parsed.get("feedback", "") or task))[:1000]
    conv.ended_at = datetime.utcnow()
    db.commit()

    return render(request, "writing_result.html", db=db,
                  task=task, original=text, result=parsed)
