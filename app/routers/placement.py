"""Срез знаний — определить стартовый уровень CEFR по узнаванию слов.

Показываем слова с разных уровней (A1..C2), ученик выбирает перевод. Уровень,
на котором узнавание проседает, — точка старта. Только данные словаря, без API.
"""
import json
import random

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.activity import touch_session
from app.config import CEFR_ORDER
from app.database import get_db
from app.deps import get_current_user
from app.models import Word
from app.seed import generate_cards_for_user
from app.templating import render

router = APIRouter()

PER_LEVEL = 6      # слов на уровень
PASS = 0.7         # порог «уровень освоен»


@router.get("/placement")
def placement(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    questions = []
    for lv in CEFR_ORDER:
        words = [w for w in db.query(Word).filter(Word.cefr_level == lv).all() if w.back.strip()]
        random.shuffle(words)
        picked = words[:PER_LEVEL]
        pool = list({w.back for w in words})          # обманки того же уровня
        for w in picked:
            distr = [b for b in pool if b.strip().lower() != w.back.strip().lower()]
            random.shuffle(distr)
            options = [w.back] + distr[:2]
            random.shuffle(options)
            questions.append({"level": lv, "word": w.front,
                              "correct": w.back, "options": options})
    random.shuffle(questions)     # вперемешку, чтобы уровни не читались по порядку

    return render(request, "placement.html", db=db,
                  questions_json=json.dumps(questions, ensure_ascii=False),
                  levels=CEFR_ORDER, per_level=PER_LEVEL, pass_pct=int(PASS * 100),
                  has_questions=bool(questions))


@router.post("/placement/apply")
def placement_apply(request: Request, level: str = Form(...), db: Session = Depends(get_db)):
    """Применить результат: выставить уровень и доложить стартовые карточки."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    lv = (level or "").strip().upper()
    if lv in CEFR_ORDER:
        user.cefr_level = lv
        db.commit()
        generate_cards_for_user(db, user)   # добрать стартовые карточки нового уровня
        touch_session(db, user.id, "placement", f"Срез знаний: старт с уровня {lv}")
    return RedirectResponse("/dashboard", status_code=303)
