"""Игры — разнообразные игровые тренировки словаря поверх колоды ученика.

Пока: «Собери слово из букв». Игры читают слова из общей памяти (карточки),
результат пишут сессией (активность/отчёт), FSRS не трогают.
"""

import json
import random
import string

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
PICTURE_ROUNDS = 8
AUDIO_ROUNDS = 8
PAIRS_COUNT = 6
WORD_ROUNDS = 8       # анаграмма / виселица
MISSING_ROUNDS = 10
SPEED_ROUNDS = 30     # с запасом под таймер
MEMORY_PAIRS = 6


class DoneIn(BaseModel):
    solved: int = 0
    total: int = 0


def _mcq_rounds(cards, prompt_pool, n, front_prompt):
    """Собрать MCQ-раунды. front_prompt=True → в вопросе английское слово (для аудио),
    иначе — эмодзи (для картинок). prompt_pool — карточки-кандидаты в вопрос."""
    all_fronts = [c.front for c in cards]
    random.shuffle(prompt_pool)
    rounds = []
    for c in prompt_pool[:n]:
        distr = [f for f in all_fronts if f.strip().lower() != c.front.strip().lower()]
        random.shuffle(distr)
        options = [c.front] + distr[:2]
        random.shuffle(options)
        r = {"correct": c.front, "options": options}
        r["word" if front_prompt else "emoji"] = c.front if front_prompt else emoji_for(c.front)
        rounds.append(r)
    return rounds


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


@router.get("/games/picture")
def games_picture(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    cards = db.query(Card).filter(Card.user_id == user.id).all()
    with_emoji = [c for c in cards if emoji_for(c.front)]  # только слова с картинкой
    rounds = _mcq_rounds(cards, with_emoji, PICTURE_ROUNDS, front_prompt=False)
    return render(request, "games_picture.html", db=db,
                  rounds_json=json.dumps(rounds, ensure_ascii=False), has_rounds=bool(rounds))


@router.get("/games/audio")
def games_audio(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    cards = db.query(Card).filter(Card.user_id == user.id).all()
    speakable = [c for c in cards if c.front.replace(" ", "").isalpha()]
    rounds = _mcq_rounds(cards, speakable, AUDIO_ROUNDS, front_prompt=True)
    return render(request, "games_audio.html", db=db,
                  rounds_json=json.dumps(rounds, ensure_ascii=False), has_rounds=bool(rounds))


@router.get("/games/pairs")
def games_pairs(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    cards = db.query(Card).filter(Card.user_id == user.id).all()
    random.shuffle(cards)
    pairs = [{"id": i, "en": c.front, "ru": c.back} for i, c in enumerate(cards[:PAIRS_COUNT])]
    return render(request, "games_pairs.html", db=db,
                  pairs_json=json.dumps(pairs, ensure_ascii=False), has_pairs=len(pairs) >= 3)


def _words(cards):
    return [c for c in cards if c.front.isalpha() and 3 <= len(c.front) <= 9]


@router.get("/games/anagram")
def games_anagram(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    good = _words(db.query(Card).filter(Card.user_id == user.id).all())
    random.shuffle(good)
    rounds = [{"word": c.front, "clue": c.back} for c in good[:WORD_ROUNDS]]
    return render(request, "games_anagram.html", db=db,
                  rounds_json=json.dumps(rounds, ensure_ascii=False), has_rounds=bool(rounds))


@router.get("/games/hangman")
def games_hangman(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    good = _words(db.query(Card).filter(Card.user_id == user.id).all())
    random.shuffle(good)
    rounds = [{"word": c.front, "clue": c.back} for c in good[:WORD_ROUNDS]]
    return render(request, "games_hangman.html", db=db,
                  rounds_json=json.dumps(rounds, ensure_ascii=False), has_rounds=bool(rounds))


@router.get("/games/missing")
def games_missing(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    good = [c for c in db.query(Card).filter(Card.user_id == user.id).all()
            if c.front.isalpha() and 3 <= len(c.front) <= 10]
    random.shuffle(good)
    rounds = []
    for c in good[:MISSING_ROUNDS]:
        w = c.front
        pos = random.randrange(len(w))
        correct = w[pos].lower()
        blanked = w[:pos] + "·" + w[pos + 1:]
        others = [x for x in string.ascii_lowercase if x != correct]
        random.shuffle(others)
        options = [correct] + others[:2]
        random.shuffle(options)
        rounds.append({"blanked": blanked, "correct": correct, "options": options, "clue": c.back})
    return render(request, "games_missing.html", db=db,
                  rounds_json=json.dumps(rounds, ensure_ascii=False), has_rounds=bool(rounds))


@router.get("/games/speed")
def games_speed(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    cards = db.query(Card).filter(Card.user_id == user.id).all()
    if len(cards) < 3:
        rounds = []
    else:
        fronts = [c.front for c in cards]
        backs = [c.back for c in cards]
        seq = cards[:]
        while len(seq) < SPEED_ROUNDS:
            seq = seq + cards
        random.shuffle(seq)
        rounds = []
        for c in seq[:SPEED_ROUNDS]:
            if random.random() < 0.5:
                prompt, correct, pool = c.front, c.back, backs
            else:
                prompt, correct, pool = c.back, c.front, fronts
            distr = [x for x in pool if x.strip().lower() != correct.strip().lower()]
            random.shuffle(distr)
            options = [correct] + distr[:2]
            random.shuffle(options)
            rounds.append({"prompt": prompt, "correct": correct, "options": options})
    return render(request, "games_speed.html", db=db,
                  rounds_json=json.dumps(rounds, ensure_ascii=False), has_rounds=bool(rounds))


@router.get("/games/memory")
def games_memory(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    cards = db.query(Card).filter(Card.user_id == user.id).all()
    random.shuffle(cards)
    pairs = [{"id": i, "en": c.front, "ru": c.back} for i, c in enumerate(cards[:MEMORY_PAIRS])]
    return render(request, "games_memory.html", db=db,
                  pairs_json=json.dumps(pairs, ensure_ascii=False), has_pairs=len(pairs) >= 3)


@router.post("/games/{game}/done")
def games_done(game: str, data: DoneIn, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "auth"}, status_code=401)
    names = {"picture": "Слово-картинка", "audio": "Аудио", "pairs": "Пары",
             "anagram": "Анаграмма", "hangman": "Виселица", "missing": "Пропущенная буква",
             "speed": "На скорость", "memory": "Мемори"}
    if game not in names:
        return JSONResponse({"error": "unknown"}, status_code=404)
    touch_session(db, user.id, f"game_{game}", f"{names[game]}: {data.solved}/{data.total}")
    return {"ok": True}
