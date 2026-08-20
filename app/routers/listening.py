"""Аудирование: генерация скрипта под уровень → озвучка (ElevenLabs) → gap-fill.

Пропуски вписываются (B1+) или выбираются из вариантов (A1–A2). Ошибки → общая
память (Mistake, source_module="listening"). Аудио кэшируется файлом.
"""

import json
import random

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app import listening_service, speaking_service
from app.activity import touch_session
from app.config import BASE_DIR, CEFR_ORDER, listening_enabled
from app.database import get_db
from app.deps import get_current_user
from app.models import ContentItem, Mistake
from app.templating import render

router = APIRouter()

AUDIO_DIR = BASE_DIR / "data" / "audio"


def _allowed_levels(user) -> list[str]:
    try:
        idx = CEFR_ORDER.index((user.cefr_level or "A1").upper())
    except ValueError:
        idx = 0
    return CEFR_ORDER[: idx + 1]


@router.get("/listening")
def listening_home(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    items = (db.query(ContentItem)
             .filter(ContentItem.kind == "listening",
                     ContentItem.cefr_level.in_(_allowed_levels(user)))
             .order_by(ContentItem.created_at.desc()).limit(30).all())
    return render(request, "listening.html", db=db, items=items, enabled=listening_enabled())


@router.post("/listening/generate")
def listening_generate(request: Request, topic: str = Form(""),
                       db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if not listening_enabled():
        return RedirectResponse("/listening", status_code=302)

    level = (user.cefr_level or "A1").upper()
    try:
        data = listening_service.generate_listening(level, topic)
    except Exception:  # noqa: BLE001
        return RedirectResponse("/listening", status_code=302)
    if not data.get("full") or not data.get("answers"):
        return RedirectResponse("/listening", status_code=302)

    item = ContentItem(title=data["title"], body=json.dumps(data, ensure_ascii=False),
                       kind="listening", cefr_level=level, topic=topic.strip(),
                       created_by=user.id)
    db.add(item)
    db.commit()
    db.refresh(item)
    return RedirectResponse(f"/listening/{item.id}", status_code=302)


def _load(db, item_id):
    item = (db.query(ContentItem)
            .filter(ContentItem.id == item_id, ContentItem.kind == "listening").first())
    if not item:
        return None, None
    try:
        return item, json.loads(item.body)
    except (json.JSONDecodeError, ValueError):
        return item, None


@router.get("/listening/{item_id}")
def listening_item(item_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    item, data = _load(db, item_id)
    if not item or not data:
        return RedirectResponse("/listening", status_code=302)

    answers = data.get("answers", [])
    segments = data.get("cloze", "").split("___")
    level = (user.cefr_level or "A1").upper()
    choice_mode = level in ("A1", "A2")
    options = None
    if choice_mode:
        options = []
        for i, ans in enumerate(answers):
            pool = [a for j, a in enumerate(answers) if j != i]
            random.shuffle(pool)
            opts = [ans] + pool[:2]
            random.shuffle(opts)
            options.append(opts)

    slow = level in ("A1", "A2")  # для новичка медленнее по умолчанию
    return render(request, "listening_item.html", db=db, item=item,
                  segments=segments, n=len(answers), options=options,
                  choice_mode=choice_mode, slow=slow, full=data.get("full", ""))


@router.get("/listening/{item_id}/audio")
def listening_audio(item_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if not listening_enabled():
        return RedirectResponse("/listening", status_code=302)
    item, data = _load(db, item_id)
    if not item or not data:
        return RedirectResponse("/listening", status_code=302)

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    path = AUDIO_DIR / f"listening_{item_id}.mp3"
    if not path.exists():
        try:
            audio = speaking_service.text_to_speech(data.get("full", "")[:2000], 1.0)
            path.write_bytes(audio)
        except Exception:  # noqa: BLE001 — нет ElevenLabs/кредитов → клиент озвучит голосом браузера
            return Response(status_code=503)
    return FileResponse(str(path), media_type="audio/mpeg")


@router.post("/listening/{item_id}/check")
async def listening_check(item_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    item, data = _load(db, item_id)
    if not item or not data:
        return RedirectResponse("/listening", status_code=302)

    answers = data.get("answers", [])
    form = await request.form()
    results, correct = [], 0
    for i, ans in enumerate(answers):
        given = str(form.get(f"a{i}", "")).strip()
        ok = given.lower() == ans.strip().lower()
        if ok:
            correct += 1
        else:
            db.add(Mistake(
                user_id=user.id, original=(given or "—")[:1000], correction=ans[:1000],
                explanation="пропущенное слово в аудио", category="listening",
                source_module="listening",
            ))
        results.append({"answer": ans, "given": given, "ok": ok})
    db.commit()
    touch_session(db, user.id, "listening", f"{item.title}: {correct}/{len(answers)}")

    return render(request, "listening_result.html", db=db,
                  item=item, results=results, correct=correct, total=len(answers))
