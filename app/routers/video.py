"""Видео: встроенный YouTube-ролик + пропуски в транскрипте (модель «Dear Kitten»).

Владелец добавляет ссылку + транскрипт; AI выбирает ключевые слова для пропусков.
Ученик смотрит видео и вписывает/выбирает услышанное. Ошибки → общая память.
Смотреть можно без ключей; для добавления нужен Claude (выбор пропусков).
"""

import html
import json
import random
import re

import httpx
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.activity import touch_session
from app.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, CEFR_ORDER, reading_enabled
from app.database import get_db
from app.deps import get_current_user
from app.models import ContentItem
from app.templating import render

router = APIRouter()


def _judge_reflection(title: str, text: str) -> dict:
    """ИИ-проверка отклика: 1-2 связных английских предложения о ролике. {ok, feedback}."""
    system = (
        "Ты проверяешь короткий отклик ученика после просмотра англоязычного ролика. "
        "Засчитай (ok=true), если это 1-2 осмысленных предложения НА АНГЛИЙСКОМ — искренняя попытка "
        "рассказать/подумать о ролике. Не придирайся к грамматике и к тому, точно ли по теме — "
        "главное, что написано по-английски и осмысленно. ok=false только если пусто, не по-английски "
        "или бессмыслица/случайный набор. Дай короткий доброжелательный feedback по-русски. "
        'Верни СТРОГО JSON: {"ok": true/false, "feedback": "..."}.'
    )
    user = "Ролик: " + (title or "")[:150] + "\nОтклик ученика:\n" + (text or "")[:1500]
    try:
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": ANTHROPIC_MODEL, "max_tokens": 300, "system": system,
                  "messages": [{"role": "user", "content": user}]},
            timeout=40,
        )
        r.raise_for_status()
        txt = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
        txt = txt.strip()
        if txt.startswith("```"):
            txt = re.sub(r"^```[a-zA-Z]*\n?", "", txt).rstrip("`").strip()
        m = re.search(r"\{.*\}", txt, re.S)
        d = json.loads(m.group(0) if m else txt)
        return {"ok": bool(d.get("ok")), "feedback": str(d.get("feedback", ""))[:500]}
    except Exception:  # noqa: BLE001
        return {"ok": False, "feedback": ""}

_YT = re.compile(r"(?:v=|youtu\.be/|embed/|shorts/)([A-Za-z0-9_-]{11})")


def _youtube_id(url: str) -> str:
    m = _YT.search(url or "")
    return m.group(1) if m else ""


def fetch_transcript(video_id: str) -> str:
    """Best-effort: подтянуть субтитры ролика с YouTube (англ. приоритетно).

    Берём страницу watch, находим captionTracks, тянем timedtext, склеиваем текст.
    Если субтитров нет / YouTube не отдал — вернём пустую строку (тогда просим вставить вручную).
    """
    try:
        page = httpx.get(
            "https://www.youtube.com/watch?v=" + video_id,
            headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9"},
            timeout=20, follow_redirects=True,
        ).text
        # достаём пары (ссылка на субтитры, код языка) — устойчиво к вложенным скобкам в строках
        pairs = re.findall(
            r'"baseUrl":"(https://www\.youtube\.com/api/timedtext[^"]+)".*?"languageCode":"([a-zA-Z-]+)"',
            page)
        if not pairs:
            return ""
        base = next((u for u, lang in pairs if lang.startswith("en")), pairs[0][0])
        base = base.replace("\\u0026", "&")            # экранированные & в URL
        cap = httpx.get(base, headers={"User-Agent": "Mozilla/5.0"}, timeout=20).text
        segs = re.findall(r"<text[^>]*>(.*?)</text>", cap, re.S)
        text = " ".join(html.unescape(re.sub(r"<[^>]+>", "", s)).strip() for s in segs)
        return re.sub(r"\s+", " ", text).strip()
    except Exception:  # noqa: BLE001
        return ""


def _allowed_levels(user) -> list[str]:
    try:
        idx = CEFR_ORDER.index((user.cefr_level or "A1").upper())
    except ValueError:
        idx = 0
    return CEFR_ORDER[: idx + 1]


_ERRORS = {
    "url": "Не распознал ссылку YouTube. Нужен адрес вида youtube.com/watch?v=… или youtu.be/…",
    "transcript": "У ролика не нашлись субтитры автоматически — вставь текст (субтитры) в поле «Транскрипт».",
    "cloze": "Не удалось разобрать транскрипт. Проверь, что это английский текст ролика.",
}


@router.get("/video")
def video_home(request: Request, err: str = "", db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    items = (db.query(ContentItem)
             .filter(ContentItem.kind == "video",
                     ContentItem.cefr_level.in_(_allowed_levels(user)))
             .order_by(func.random()).limit(48).all())   # свежая подборка каждый раз
    return render(request, "video.html", db=db, items=items, can_add=reading_enabled(),
                  error=_ERRORS.get(err, ""))


@router.post("/video/add")
def video_add(request: Request, url: str = Form(""), title: str = Form(""),
              db: Session = Depends(get_db)):
    """Добавить ролик — нужна только ссылка YouTube (упражнение — отклик, не клоуз)."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    yt = _youtube_id(url)
    if not yt:
        return RedirectResponse("/video?err=url", status_code=303)
    level = (user.cefr_level or "A1").upper()
    body = {"youtube": yt}
    item = ContentItem(title=(title.strip() or "Видео")[:120], body=json.dumps(body, ensure_ascii=False),
                       kind="video", cefr_level=level, created_by=user.id)
    db.add(item)
    db.commit()
    db.refresh(item)
    return RedirectResponse(f"/video/{item.id}", status_code=303)


def _load(db, item_id):
    item = (db.query(ContentItem)
            .filter(ContentItem.id == item_id, ContentItem.kind == "video").first())
    if not item:
        return None, None
    try:
        return item, json.loads(item.body)
    except (json.JSONDecodeError, ValueError):
        return item, None


@router.get("/video/{item_id}")
def video_item(item_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    item, data = _load(db, item_id)
    if not item or not data:
        return RedirectResponse("/video", status_code=302)
    return render(request, "video_item.html", db=db, item=item, youtube=data.get("youtube", ""))


@router.post("/video/{item_id}/reflect")
def video_reflect(item_id: int, request: Request, text: str = Form(""),
                  db: Session = Depends(get_db)):
    """Проверка после просмотра: 1-2 предложения по-английски о ролике (оценивает ИИ)."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    item, data = _load(db, item_id)
    if not item or not data:
        return RedirectResponse("/video", status_code=302)
    text = (text or "").strip()
    res = _judge_reflection(item.title, text)
    if res["ok"]:
        touch_session(db, user.id, "video", f"{item.title}: отклик")
    return render(request, "video_result.html", db=db, item=item,
                  youtube=data.get("youtube", ""), text=text,
                  ok=res["ok"], feedback=res["feedback"])
