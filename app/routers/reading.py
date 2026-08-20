"""Чтение: список текстов, генерация под уровень, ридер с тап-переводом.

Перевод всех слов текста строится один раз (глоссарий) → наведение мгновенное.
Клик по слову → «в карточки» через ту же логику, что и ручной ввод (единая память).
"""

import json

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
from app.seed import add_words_for_user
from app.templating import render

router = APIRouter()


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


@router.get("/reading/{item_id}")
def reading_item(item_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    item = db.query(ContentItem).filter(ContentItem.id == item_id).first()
    if not item:
        return RedirectResponse("/reading", status_code=302)
    # Старые тексты без глоссария — соберём один раз при первом открытии.
    if not item.glossary and reading_enabled():
        try:
            item.glossary = json.dumps(reading_service.build_glossary(item.body), ensure_ascii=False)
            db.commit()
        except Exception:  # noqa: BLE001
            pass
    touch_session(db, user.id, "reading", item.title)
    return render(request, "reading_item.html", db=db, item=item, enabled=reading_enabled())


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
