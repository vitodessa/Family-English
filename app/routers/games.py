"""Игры — разнообразные игровые тренировки словаря поверх колоды ученика.

Пока: «Собери слово из букв». Игры читают слова из общей памяти (карточки),
результат пишут сессией (активность/отчёт), FSRS не трогают.
"""

import json
import random

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.activity import touch_session
from app.database import get_db
from app.deps import get_current_user
from app.emoji_map import emoji_for
from app.models import Card
from app.templating import render

router = APIRouter()

SPELL_ROUNDS = 8


class DoneIn(BaseModel):
    solved: int = 0
    total: int = 0


@router.get("/games")
def games_home(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    return render(request, "games.html", db=db)


def _spell_rounds(db: Session, user, n: int) -> list[dict]:
    cards = db.query(Card).filter(Card.user_id == user.id).all()
    # только одиночные латинские слова разумной длины
    good = [c for c in cards if c.front.isalpha() and 2 <= len(c.front) <= 10]
    random.shuffle(good)
    return [{"word": c.front, "emoji": emoji_for(c.front), "clue": c.back}
            for c in good[:n]]


@router.get("/games/spell")
def games_spell(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    rounds = _spell_rounds(db, user, SPELL_ROUNDS)
    return render(request, "games_spell.html", db=db,
                  rounds_json=json.dumps(rounds, ensure_ascii=False),
                  has_rounds=bool(rounds))


@router.post("/games/spell/done")
def games_spell_done(data: DoneIn, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "auth"}, status_code=401)
    touch_session(db, user.id, "game_spell", f"Собери слово: {data.solved}/{data.total}")
    return {"ok": True}
