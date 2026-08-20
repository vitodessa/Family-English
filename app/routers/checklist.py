"""Чек-лист уровня: вехи освоения, ученик отмечает пройденное (сохраняется)."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.checklists import CHECKLISTS
from app.database import get_db
from app.deps import get_current_user
from app.models import ChecklistCheck
from app.templating import render

router = APIRouter()


@router.get("/checklist")
def checklist_home(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    level = (user.cefr_level or "A1").upper()
    items = CHECKLISTS.get(level, [])
    checked = {c.item_key for c in db.query(ChecklistCheck)
               .filter(ChecklistCheck.user_id == user.id).all()}
    rows = [{"idx": i, "text": t, "key": f"{level}:{i}", "done": f"{level}:{i}" in checked}
            for i, t in enumerate(items)]
    done = sum(1 for r in rows if r["done"])
    return render(request, "checklist.html", db=db, level=level, rows=rows,
                  done=done, total=len(rows))


@router.post("/checklist/toggle")
def checklist_toggle(request: Request, key: str = Form(...),
                     db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    existing = (db.query(ChecklistCheck)
                .filter(ChecklistCheck.user_id == user.id,
                        ChecklistCheck.item_key == key).first())
    if existing:
        db.delete(existing)
    else:
        db.add(ChecklistCheck(user_id=user.id, item_key=key))
    db.commit()
    return RedirectResponse("/checklist", status_code=302)
