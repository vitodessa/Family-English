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
from sqlalchemy.orm import Session

from app import listening_service
from app.activity import touch_session
from app.config import CEFR_ORDER, reading_enabled
from app.database import get_db
from app.deps import get_current_user
from app.models import ContentItem, Mistake
from app.templating import render

router = APIRouter()

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
             .order_by(ContentItem.created_at.desc()).limit(30).all())
    return render(request, "video.html", db=db, items=items, can_add=reading_enabled(),
                  error=_ERRORS.get(err, ""))


@router.post("/video/add")
def video_add(request: Request, url: str = Form(""), title: str = Form(""),
              transcript: str = Form(""), db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if not reading_enabled():
        return RedirectResponse("/video", status_code=302)

    yt = _youtube_id(url)
    if not yt:
        return RedirectResponse("/video?err=url", status_code=303)

    transcript = (transcript or "").strip()
    if len(transcript) < 20:                       # нет транскрипта — тянем субтитры сами
        transcript = fetch_transcript(yt)
    if len(transcript) < 20:
        return RedirectResponse("/video?err=transcript", status_code=303)

    level = (user.cefr_level or "A1").upper()
    try:
        answers = listening_service.pick_blanks(transcript, level)
        cloze, used = listening_service._build_cloze(transcript, answers)
    except Exception:  # noqa: BLE001
        return RedirectResponse("/video?err=cloze", status_code=303)
    if not used:
        return RedirectResponse("/video?err=cloze", status_code=303)

    body = {"youtube": yt, "full": transcript, "cloze": cloze, "answers": used}
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
    return render(request, "video_item.html", db=db, item=item, youtube=data.get("youtube", ""),
                  segments=segments, n=len(answers), options=options, choice_mode=choice_mode)


@router.post("/video/{item_id}/check")
async def video_check(item_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    item, data = _load(db, item_id)
    if not item or not data:
        return RedirectResponse("/video", status_code=302)

    answers = data.get("answers", [])
    form = await request.form()
    results, correct = [], 0
    for i, ans in enumerate(answers):
        given = str(form.get(f"a{i}", "")).strip()
        ok = given.lower() == ans.strip().lower()
        if ok:
            correct += 1
        else:
            db.add(Mistake(user_id=user.id, original=(given or "—")[:1000], correction=ans[:1000],
                           explanation="пропущенное слово в видео", category="listening",
                           source_module="video"))
        results.append({"answer": ans, "given": given, "ok": ok})
    db.commit()
    touch_session(db, user.id, "video", f"{item.title}: {correct}/{len(answers)}")
    return render(request, "video_result.html", db=db,
                  item=item, results=results, correct=correct, total=len(answers))
