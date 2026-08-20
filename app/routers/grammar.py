"""Грамматика: темы → теория (кэш) + клоуз-практика («впиши правильную форму»).

Ошибки практики пишутся в Mistake с grammar_topic_id — грамматический дашборд
«вырастает сам» из этих тегов.
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app import grammar_service
from app.config import grammar_enabled
from app.database import get_db
from app.deps import get_current_user
from app.models import GrammarLesson, GrammarTopic, Mistake
from app.templating import render

router = APIRouter()


def _theory_for(db: Session, topic: GrammarTopic, level: str) -> str:
    """Взять теорию из кэша или сгенерировать один раз под (тема, уровень)."""
    level = (level or "A1").upper()
    lesson = (db.query(GrammarLesson)
              .filter(GrammarLesson.grammar_topic_id == topic.id,
                      GrammarLesson.cefr_level == level).first())
    if lesson and lesson.theory:
        return lesson.theory
    theory = grammar_service.generate_theory(topic.name, level)
    if not lesson:
        lesson = GrammarLesson(grammar_topic_id=topic.id, cefr_level=level, theory=theory)
        db.add(lesson)
    else:
        lesson.theory = theory
    db.commit()
    return theory


@router.get("/grammar")
def grammar_home(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    topics = db.query(GrammarTopic).order_by(GrammarTopic.id).all()
    return render(request, "grammar.html", db=db, topics=topics, enabled=grammar_enabled())


@router.get("/grammar/{topic_id}")
def grammar_topic(topic_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    topic = db.query(GrammarTopic).filter(GrammarTopic.id == topic_id).first()
    if not topic:
        return RedirectResponse("/grammar", status_code=302)
    theory = _theory_for(db, topic, user.cefr_level) if grammar_enabled() else ""
    return render(request, "grammar_topic.html", db=db,
                  topic=topic, theory=theory, enabled=grammar_enabled())


@router.get("/grammar/{topic_id}/practice")
def grammar_practice(topic_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    topic = db.query(GrammarTopic).filter(GrammarTopic.id == topic_id).first()
    if not topic or not grammar_enabled():
        return RedirectResponse(f"/grammar/{topic_id}", status_code=302)
    items = grammar_service.generate_cloze(topic.name, user.cefr_level or "A1")
    return render(request, "grammar_practice.html", db=db, topic=topic, items=items)


@router.post("/grammar/{topic_id}/check")
def grammar_check(
    topic_id: int,
    request: Request,
    sentence: list[str] = Form(default=[]),
    answer: list[str] = Form(default=[]),
    given: list[str] = Form(default=[]),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    topic = db.query(GrammarTopic).filter(GrammarTopic.id == topic_id).first()
    if not topic:
        return RedirectResponse("/grammar", status_code=302)

    results, correct = [], 0
    for i, ans in enumerate(answer):
        you = given[i].strip() if i < len(given) else ""
        sent = sentence[i] if i < len(sentence) else ""
        ok = you.lower() == ans.strip().lower()
        if ok:
            correct += 1
        else:
            # ошибка → в общую память, с тегом грамматической темы
            db.add(Mistake(
                user_id=user.id, grammar_topic_id=topic.id,
                original=(you or "—")[:1000], correction=ans[:1000],
                explanation=sent[:1000], category="grammar", source_module="grammar",
            ))
        results.append({"sentence": sent, "answer": ans, "given": you, "ok": ok})
    db.commit()

    return render(request, "grammar_result.html", db=db,
                  topic=topic, results=results, correct=correct, total=len(answer))
