"""Челлендж: геймифицированный тест с жизнями (❤️❤️❤️) по словам ученика.

ED-фича #5. Быстрый MCQ: ошибся — минус жизнь, кончились — конец. Считаем счёт и
серию. Результат пишется сессией (для активности/отчёта). FSRS не трогаем — это игра.
"""

import json
import random

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.activity import touch_session
from app.config import CHALLENGE_QUESTIONS
from app.database import get_db
from app.deps import get_current_user
from app.models import Card
from app.templating import render

router = APIRouter()


class DoneIn(BaseModel):
    score: int = 0
    total: int = 0
    won: bool = False


def _questions(db: Session, user, n: int) -> list[dict]:
    cards = db.query(Card).filter(Card.user_id == user.id).all()
    if len(cards) < 3:
        return []
    random.shuffle(cards)
    fronts = [c.front for c in cards]
    backs = [c.back for c in cards]
    # если карточек мало — допускаем повторы, но перемешиваем
    seq = cards[:] if len(cards) >= n else (cards * (n // len(cards) + 1))
    random.shuffle(seq)

    qs = []
    for card in seq[:n]:
        if random.random() < 0.5:                       # EN → RU
            prompt, correct, pool = card.front, card.back, backs
        else:                                           # RU → EN
            prompt, correct, pool = card.back, card.front, fronts
        distr = [x for x in pool if x.strip().lower() != correct.strip().lower()]
        random.shuffle(distr)
        options = [correct] + distr[:2]
        random.shuffle(options)
        qs.append({"prompt": prompt, "correct": correct, "options": options})
    return qs


@router.get("/challenge")
def challenge_home(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    questions = _questions(db, user, CHALLENGE_QUESTIONS)
    return render(request, "challenge.html", db=db,
                  questions_json=json.dumps(questions, ensure_ascii=False),
                  has_questions=bool(questions))


@router.post("/challenge/done")
def challenge_done(data: DoneIn, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "auth"}, status_code=401)
    verdict = "победа" if data.won else "не пройден"
    touch_session(db, user.id, "challenge", f"Челлендж: {data.score}/{data.total} ({verdict})")
    return {"ok": True}
