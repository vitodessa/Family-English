"""Speaking: страница разговора + API ходов и озвучки."""

from datetime import datetime

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from app import speaking_service
from app.config import speaking_enabled
from app.database import get_db
from app.deps import get_current_user
from app.models import Session as ConvSession
from app.templating import render

router = APIRouter()


class TurnIn(BaseModel):
    session_id: int
    history: list[dict]
    topic: str = ""


class TtsIn(BaseModel):
    text: str


@router.get("/speaking")
def speaking_page(request: Request, db: DBSession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    return render(request, "speaking.html", db=db, enabled=speaking_enabled())


@router.post("/speaking/start")
def speaking_start(request: Request, db: DBSession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "auth"}, status_code=401)
    if not speaking_enabled():
        return JSONResponse({"error": "Модуль не настроен (нет ключей)"}, status_code=503)

    conv = ConvSession(user_id=user.id, module="speaking")
    db.add(conv)
    db.commit()
    db.refresh(conv)

    seed = [{"role": "user", "content": "Let's begin the lesson."}]
    try:
        result = speaking_service.chat_turn(db, user, conv.id, seed)
    except Exception as e:  # noqa: BLE001 — показываем человеку понятную ошибку
        return JSONResponse({"error": f"Не удалось обратиться к ИИ: {e}"}, status_code=502)

    return {"session_id": conv.id, **result}


@router.post("/speaking/turn")
def speaking_turn(data: TurnIn, request: Request, db: DBSession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "auth"}, status_code=401)
    if not speaking_enabled():
        return JSONResponse({"error": "Модуль не настроен"}, status_code=503)

    conv = (db.query(ConvSession)
            .filter(ConvSession.id == data.session_id, ConvSession.user_id == user.id)
            .first())
    if not conv:
        return JSONResponse({"error": "Сессия не найдена"}, status_code=404)

    try:
        result = speaking_service.chat_turn(db, user, conv.id, data.history, data.topic)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"Ошибка ИИ: {e}"}, status_code=502)
    return result


@router.post("/speaking/tts")
def speaking_tts(data: TtsIn, request: Request, db: DBSession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "auth"}, status_code=401)
    if not speaking_enabled():
        return JSONResponse({"error": "Модуль не настроен"}, status_code=503)
    try:
        audio = speaking_service.text_to_speech(data.text[:1500])
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"Ошибка озвучки: {e}"}, status_code=502)
    return Response(content=audio, media_type="audio/mpeg")


@router.post("/speaking/end")
def speaking_end(data: TurnIn, request: Request, db: DBSession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "auth"}, status_code=401)
    conv = (db.query(ConvSession)
            .filter(ConvSession.id == data.session_id, ConvSession.user_id == user.id)
            .first())
    if conv and not conv.ended_at:
        conv.ended_at = datetime.utcnow()
        db.commit()
    return {"ok": True}
