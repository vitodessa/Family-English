"""Ачивки: сетка бейджей (получено/заперто), считается из данных без API."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.achievements import earned_achievements
from app.database import get_db
from app.deps import get_current_user
from app.templating import render

router = APIRouter()


@router.get("/achievements")
def achievements_home(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    items = earned_achievements(db, user)
    done = sum(1 for a in items if a["done"])
    return render(request, "achievements.html", db=db,
                  items=items, done=done, total=len(items))
