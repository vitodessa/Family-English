"""Семейный фид: активность всех + новые слова. Цифровизация семейного чата (без API)."""

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app import token_service
from app.database import get_db
from app.deps import get_current_user
from app.models import LearningEvent, User
from app.models import Session as ConvSession
from app.templating import render

router = APIRouter()

MODULE_LABEL = {
    "lesson_test": ("✅", "прошёл(ла) Урок дня"),
    "speaking": ("🎤", "говорил(а) с AI"),
    "writing": ("✍️", "писал(а)"),
    "reading": ("📖", "читал(а)"),
    "grammar": ("📚", "занимался(лась) грамматикой"),
    "listening": ("🎧", "слушал(а)"),
    "video": ("🎬", "смотрел(а) видео"),
    "challenge": ("🎯", "прошёл(ла) Челлендж"),
    "game_spell": ("🔤", "собирал(а) слова"),
    "game_picture": ("🖼", "играл(а) в «Слово-картинку»"),
    "game_pairs": ("🧩", "искал(а) пары"),
    "game_audio": ("🔊", "играл(а) в «Аудио»"),
    "game_anagram": ("🔀", "разгадывал(а) анаграммы"),
    "game_hangman": ("🎯", "играл(а) в «Виселицу»"),
    "game_missing": ("🔤", "искал(а) пропущенные буквы"),
    "game_speed": ("⏱", "играл(а) на скорость"),
    "game_memory": ("🧠", "играл(а) в «Мемори»"),
}


def _day_start() -> datetime:
    d = datetime.utcnow().date()
    return datetime(d.year, d.month, d.day)


@router.get("/family")
def family_home(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    users = db.query(User).order_by(User.id).all()
    names = {u.id: u.name for u in users}
    ds = _day_start()

    members = []
    for u in users:
        members.append({
            "name": u.name, "level": u.cefr_level,
            "tokens": token_service.balance(db, u.id),
            "streak": token_service.lesson_streak(db, u.id),
            "reviews_today": db.query(LearningEvent)
            .filter(LearningEvent.user_id == u.id, LearningEvent.reviewed_at >= ds).count(),
        })

    sessions = (db.query(ConvSession)
                .order_by(ConvSession.started_at.desc()).limit(60).all())
    feed = []
    for s in sessions:
        lab = MODULE_LABEL.get(s.module)
        if not lab:
            continue
        feed.append({"name": names.get(s.user_id, "?"), "icon": lab[0],
                     "action": lab[1], "summary": s.summary or "", "at": s.started_at})
        if len(feed) >= 30:
            break

    return render(request, "family.html", db=db, members=members, feed=feed)
