"""Чтение: список текстов, генерация под уровень, ридер с тап-переводом.

Перевод всех слов текста строится один раз (глоссарий) → наведение мгновенное.
Клик по слову → «в карточки» через ту же логику, что и ручной ввод (единая память).
"""

import json
from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import reading_service
from app.activity import touch_session
from app.config import CEFR_ORDER, reading_enabled
from app.database import get_db
from app.deps import get_current_user
from app.models import ContentItem, Word
from app.models import Session as ConvSession
from app.seed import add_words_for_user
from app.templating import render

router = APIRouter()

READ_PASS = 50   # порог точности чтения вслух, %
TR_PASS = 50     # порог оценки перевода


def _day_start() -> datetime:
    d = datetime.utcnow().date()
    return datetime(d.year, d.month, d.day)


def _did_reading_r1(db, user_id: int) -> bool:
    return (db.query(ConvSession)
            .filter(ConvSession.user_id == user_id, ConvSession.module == "reading_r1_done",
                    ConvSession.started_at >= _day_start()).first()) is not None


def _plain_source(item) -> str:
    """Текст для чтения вслух: тело текста или склейка фраз."""
    if item.kind == "phrases":
        try:
            ph = json.loads(item.body or "[]")
        except (json.JSONDecodeError, ValueError):
            ph = []
        return " ".join(str(p.get("phrase", "")) for p in ph)
    return item.body or ""


def _allowed_levels(user) -> list[str]:
    try:
        idx = CEFR_ORDER.index((user.cefr_level or "A1").upper())
    except ValueError:
        idx = 0
    return CEFR_ORDER[: idx + 1]


class TranslateIn(BaseModel):
    word: str
    sentence: str = ""


class AddWordIn(BaseModel):
    word: str
    translation: str


class TranscriptIn(BaseModel):
    transcript: str = ""


@router.get("/reading")
def reading_home(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    items = (db.query(ContentItem)
             .filter(ContentItem.cefr_level.in_(_allowed_levels(user)))
             .order_by(ContentItem.created_at.desc()).limit(50).all())
    return render(request, "reading.html", db=db, items=items, enabled=reading_enabled())


@router.post("/reading/generate")
def reading_generate(
    request: Request,
    topic: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if not reading_enabled():
        return RedirectResponse("/reading", status_code=302)

    level = (user.cefr_level or "A1").upper()
    try:
        title, body = reading_service.generate_text(level, topic)
    except Exception:  # noqa: BLE001 — вернём на страницу, не роняем
        return RedirectResponse("/reading", status_code=302)
    if not body:
        return RedirectResponse("/reading", status_code=302)

    item = ContentItem(title=title, body=body, cefr_level=level,
                       topic=topic.strip(), created_by=user.id)
    # Глоссарий сразу при генерации — чтобы ридер открылся уже готовым к мгновенному переводу.
    try:
        item.glossary = json.dumps(reading_service.build_glossary(body), ensure_ascii=False)
    except Exception:  # noqa: BLE001 — глоссарий не критичен, соберём лениво при открытии
        item.glossary = ""
    db.add(item)
    db.commit()
    db.refresh(item)
    return RedirectResponse(f"/reading/{item.id}", status_code=302)


@router.post("/reading/generate-phrases")
def reading_generate_phrases(request: Request, topic: str = Form(""),
                             db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if not reading_enabled():
        return RedirectResponse("/reading", status_code=302)

    level = (user.cefr_level or "A1").upper()
    try:
        phrases = reading_service.generate_phrases(level, topic)
    except Exception:  # noqa: BLE001
        return RedirectResponse("/reading", status_code=302)
    if not phrases:
        return RedirectResponse("/reading", status_code=302)

    title = ("Фразы: " + topic.strip()) if topic.strip() else "Полезные фразы"
    item = ContentItem(title=title[:120], body=json.dumps(phrases, ensure_ascii=False),
                       kind="phrases", cefr_level=level, topic=topic.strip(), created_by=user.id)
    db.add(item)
    db.commit()
    db.refresh(item)
    return RedirectResponse(f"/reading/{item.id}", status_code=302)


@router.get("/reading/{item_id}")
def reading_item(item_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    item = db.query(ContentItem).filter(ContentItem.id == item_id).first()
    if not item:
        return RedirectResponse("/reading", status_code=302)

    if item.kind == "phrases":
        try:
            phrases = json.loads(item.body or "[]")
        except (json.JSONDecodeError, ValueError):
            phrases = []
        return render(request, "reading_phrases.html", db=db, item=item, phrases=phrases,
                      enabled=reading_enabled())
    # Старые тексты без глоссария — соберём один раз при первом открытии.
    if not item.glossary and reading_enabled():
        try:
            item.glossary = json.dumps(reading_service.build_glossary(item.body), ensure_ascii=False)
            db.commit()
        except Exception:  # noqa: BLE001
            pass
    return render(request, "reading_item.html", db=db, item=item, enabled=reading_enabled())


@router.post("/reading/{item_id}/read-check")
def reading_read_check(item_id: int, request: Request, data: TranscriptIn,
                       db: Session = Depends(get_db)):
    """Раунд 1: чтение вслух. Сверяем распознанное с текстом → точность."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "auth"}, status_code=401)
    item = db.query(ContentItem).filter(ContentItem.id == item_id).first()
    if not item:
        return JSONResponse({"error": "нет текста"}, status_code=404)
    pct, missed = reading_service.read_accuracy(_plain_source(item), data.transcript)
    passed = pct >= READ_PASS
    if passed:
        touch_session(db, user.id, "reading_r1_done", f"Чтение вслух: {pct}%")
    return {"pct": pct, "missed": missed, "passed": passed, "need": READ_PASS}


@router.post("/reading/{item_id}/translate-check")
def reading_translate_check(item_id: int, request: Request, data: TranscriptIn,
                            db: Session = Depends(get_db)):
    """Раунд 2: устный перевод на русский. Оценивает Claude; при успехе — блок зачтён."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "auth"}, status_code=401)
    if not reading_enabled():
        return JSONResponse({"error": "ИИ не настроен"}, status_code=503)
    item = db.query(ContentItem).filter(ContentItem.id == item_id).first()
    if not item:
        return JSONResponse({"error": "нет текста"}, status_code=404)
    res = reading_service.judge_translation(_plain_source(item), data.transcript,
                                            user.cefr_level or "A1")
    passed = res["score"] >= TR_PASS
    done = False
    if passed and _did_reading_r1(db, user.id):   # зачёт блока — оба раунда пройдены
        touch_session(db, user.id, "reading", item.title)
        done = True
    return {"score": res["score"], "feedback": res["feedback"],
            "passed": passed, "done": done, "need": TR_PASS}


@router.post("/reading/{item_id}/mark-read")
def reading_mark_read(item_id: int, request: Request, db: Session = Depends(get_db)):
    """Запасной зачёт, если в браузере нет распознавания речи/микрофона."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "auth"}, status_code=401)
    item = db.query(ContentItem).filter(ContentItem.id == item_id).first()
    if not item:
        return JSONResponse({"error": "нет текста"}, status_code=404)
    touch_session(db, user.id, "reading", item.title)
    return {"done": True}


@router.post("/reading/translate")
def reading_translate(data: TranslateIn, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "auth"}, status_code=401)
    if not reading_enabled():
        return JSONResponse({"error": "Чтение не настроено"}, status_code=503)
    word = (data.word or "").strip()
    if not word:
        return JSONResponse({"translation": ""})

    # Быстрый путь: слово уже в каталоге — отдаём мгновенно, без вызова AI.
    known = (db.query(Word)
             .filter(func.lower(Word.front) == word.lower())
             .first())
    if known:
        return {"word": word, "translation": known.back}

    try:
        tr = reading_service.translate_word(word, data.sentence, user.cefr_level or "")
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"Ошибка перевода: {e}"}, status_code=502)
    return {"word": word, "translation": tr}


@router.post("/reading/add-word")
def reading_add_word(data: AddWordIn, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "auth"}, status_code=401)
    word = (data.word or "").strip()
    translation = (data.translation or "").strip()
    if not word or not translation:
        return JSONResponse({"added": 0})
    added = add_words_for_user(db, user, f"{word} | {translation}")
    return {"added": added}  # 0 если слово уже есть в колоде
