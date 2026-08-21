"""Урок дня: сшивает блоки в единый ежедневный сценарий + финальный тест.

Урок — это ПРЕДСТАВЛЕНИЕ над активностью дня: готовность шага вычисляется из
того, что блоки уже пишут (сессии по модулю + повторения за сегодня).
Финальный тест — короткий MCQ по словам ученика; результат пишется сессией.
"""

import random
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.activity import touch_session
from app.config import (
    CEFR_ORDER, GAME_MODULES, LESSON_CARDS, listening_enabled, speaking_enabled,
)
from app.database import get_db
from app.deps import get_current_user
from app.models import Card, ContentItem, LearningEvent
from app.models import Session as ConvSession
from app.norms import daily_norms
from app.templating import render

router = APIRouter()

TEST_QUESTIONS = 6


def _day_start() -> datetime:
    d = datetime.utcnow().date()
    return datetime(d.year, d.month, d.day)


def _plural(n: int, one: str, few: str, many: str) -> str:
    """Русское склонение числительных: 1 слово, 2-4 слова, 5 слов."""
    nn = abs(n) % 100
    if 11 <= nn <= 14:
        return many
    d = nn % 10
    if d == 1:
        return one
    if 2 <= d <= 4:
        return few
    return many


def _did_today(db: Session, user_id: int, module: str) -> bool:
    return (db.query(ConvSession)
            .filter(ConvSession.user_id == user_id, ConvSession.module == module,
                    ConvSession.started_at >= _day_start()).first()) is not None


def _games_done_today(db: Session, user_id: int) -> int:
    """Сколько РАЗНЫХ игр из раздела пройдено сегодня (для блока «пройти все игры»)."""
    rows = (db.query(ConvSession.module)
            .filter(ConvSession.user_id == user_id,
                    ConvSession.module.in_(GAME_MODULES),
                    ConvSession.started_at >= _day_start()).all())
    return len({m for (m,) in rows})


def _allowed_levels(user) -> list:
    """Уровень ученика и ниже — для подбора контента."""
    try:
        idx = CEFR_ORDER.index((user.cefr_level or "A1").upper())
    except ValueError:
        idx = 0
    return CEFR_ORDER[:idx + 1]


def _has_video(db: Session, user) -> bool:
    """Есть ли добавленный ролик для уровня (иначе блок «Видео» нечем занять)."""
    return (db.query(ContentItem)
            .filter(ContentItem.kind == "video",
                    ContentItem.cefr_level.in_(_allowed_levels(user))).first()) is not None


def _build_steps(db: Session, user) -> list[dict]:
    reviews_today = (db.query(LearningEvent)
                     .filter(LearningEvent.user_id == user.id,
                             LearningEvent.reviewed_at >= _day_start()).count())
    n = daily_norms(db, user)   # нормы по уровню + рост со временем
    steps = [
        {"key": "cards", "icon": "🗂", "name": "Карточки",
         "desc": f"Повтори {n['cards']} {_plural(n['cards'], 'слово', 'слова', 'слов')}",
         "url": "/study", "done": reviews_today >= n["cards"]},
        {"key": "grammar", "icon": "📚", "name": "Грамматика",
         "desc": f"Теория + {n['grammar']} "
                 f"{_plural(n['grammar'], 'упражнение', 'упражнения', 'упражнений')}",
         "url": "/grammar", "done": _did_today(db, user.id, "grammar")},
        {"key": "reading", "icon": "📖", "name": "Чтение",
         "desc": "Один короткий текст", "url": "/reading",
         "done": _did_today(db, user.id, "reading")},
    ]
    if listening_enabled():
        steps.append({"key": "listening", "icon": "🎧", "name": "Аудирование",
                      "desc": "Послушать и вставить слова", "url": "/listening",
                      "done": _did_today(db, user.id, "listening")})
    steps.append({"key": "writing", "icon": "✍️", "name": "Письмо",
                  "desc": f"Написать не меньше {n['write_words']} "
                          f"{_plural(n['write_words'], 'слова', 'слов', 'слов')}",
                  "url": "/writing", "done": _did_today(db, user.id, "writing_done")})
    if speaking_enabled():
        steps.append({"key": "speaking", "icon": "🎤", "name": "Разговор",
                      "desc": f"Хотя бы {n['speak_turns']} "
                              f"{_plural(n['speak_turns'], 'реплика', 'реплики', 'реплик')}",
                      "url": "/speaking", "done": _did_today(db, user.id, "speaking_done")})
    games_done = _games_done_today(db, user.id)
    games_total = len(GAME_MODULES)
    steps.append({"key": "games", "icon": "🎮", "name": "Игры",
                  "desc": f"Пройти все игры ({games_done}/{games_total})", "url": "/games",
                  "done": games_done >= games_total})
    # Видео всегда в уроке: обязателен, если для уровня есть ролик; иначе — бонус с подсказкой
    has_v = _has_video(db, user)
    video_step = {"key": "video", "icon": "🎬", "name": "Видео",
                  "desc": "Ролик + пропущенные слова" if has_v
                          else "Добавьте ролик на странице «Видео»",
                  "url": "/video", "done": _did_today(db, user.id, "video")}
    if not has_v:
        video_step["optional"] = True
    steps.append(video_step)
    steps.append({"key": "test", "icon": "✅", "name": "Финальный тест",
                  "desc": f"{n['test']} {_plural(n['test'], 'вопрос', 'вопроса', 'вопросов')} "
                          f"по словам",
                  "url": "/lesson/test", "done": _did_today(db, user.id, "lesson_test")})
    return steps


@router.get("/lesson")
def lesson_home(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    steps = _build_steps(db, user)
    required = [s for s in steps if not s.get("optional")]
    done_required = sum(1 for s in required if s["done"])
    all_done = done_required == len(required)
    # текущий шаг — первый невыполненный (обязательный)
    current = next((s["key"] for s in steps if not s.get("optional") and not s["done"]), None)

    return render(request, "lesson.html", db=db,
                  steps=steps, done=done_required, total=len(required),
                  all_done=all_done, current=current)


def _test_questions(db: Session, user) -> list[dict]:
    cards = db.query(Card).filter(Card.user_id == user.id).all()
    if len(cards) < 3:
        return []
    random.shuffle(cards)
    backs = [c.back for c in cards]
    questions = []
    n_q = daily_norms(db, user)["test"]
    for card in cards[:n_q]:
        correct = card.back
        pool = [b for b in backs if b.strip().lower() != correct.strip().lower()]
        random.shuffle(pool)
        options = [correct] + pool[:2]
        random.shuffle(options)
        questions.append({"prompt": card.front, "correct": correct, "options": options})
    return questions


@router.get("/lesson/test")
def lesson_test(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    questions = _test_questions(db, user)
    if not questions:
        return RedirectResponse("/lesson", status_code=302)
    return render(request, "lesson_test.html", db=db, questions=questions)


@router.post("/lesson/test/submit")
async def lesson_test_submit(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    form = await request.form()
    try:
        n = int(form.get("n", "0"))
    except ValueError:
        n = 0

    results, correct = [], 0
    for i in range(n):
        prompt = str(form.get(f"prompt{i}", ""))
        answer = str(form.get(f"correct{i}", ""))
        given = str(form.get(f"q{i}", ""))
        ok = given.strip().lower() == answer.strip().lower()
        if ok:
            correct += 1
        results.append({"prompt": prompt, "answer": answer, "given": given, "ok": ok})

    touch_session(db, user.id, "lesson_test", f"Тест: {correct}/{n}")
    # Урок завершён тестом — награда токенами (если всё пройдено) + отчёт родителю.
    from app.report_service import lesson_complete, maybe_send_report
    from app.token_service import award_lesson
    tokens = award_lesson(db, user.id) if lesson_complete(db, user.id) else 0
    sent = maybe_send_report(db, user)

    return render(request, "lesson_test_result.html", db=db,
                  results=results, correct=correct, total=n, report_sent=sent, tokens=tokens)
