"""Наполнение каталога слов и подбор карточек ученику."""

import random

from sqlalchemy.orm import Session

from app.config import ADMIN_NAME, ADMIN_PASSWORD, BASE_DIR, CEFR_ORDER, INITIAL_CARDS
from app.fsrs_service import new_card_state
from app.models import Card, GrammarTopic, User, Word
from app.security import hash_password

VOCAB_DIR = BASE_DIR / "app" / "vocabulary"

# Базовый набор грамматических тем для сквозного слоя. Расширяется по ходу.
GRAMMAR_TOPICS = [
    "Present Simple",
    "Present Continuous",
    "Past Simple",
    "Future (will / going to)",
    "Present Perfect",
    "Articles (a / the)",
    "Prepositions",
    "Modal verbs",
    "Conditionals",
    "Phrasal verbs",
]


def ensure_grammar_topics(db: Session) -> int:
    """Завести базовые грамматические темы. Идемпотентно."""
    added = 0
    for name in GRAMMAR_TOPICS:
        if not db.query(GrammarTopic).filter(GrammarTopic.name == name).first():
            db.add(GrammarTopic(name=name))
            added += 1
    if added:
        db.commit()
    return added


def seed_words(db: Session) -> int:
    """Загрузить слова из app/vocabulary/<level>.txt. Идемпотентно."""
    added = 0
    for path in sorted(VOCAB_DIR.glob("*.txt")):
        level = path.stem.upper()  # a1.txt -> A1
        for raw in path.read_text(encoding="utf-8").splitlines():
            if "|" not in raw:
                continue
            front, back = (part.strip() for part in raw.split("|", 1))
            if not front or not back:
                continue
            exists = (
                db.query(Word)
                .filter(Word.front == front, Word.cefr_level == level)
                .first()
            )
            if exists:
                continue
            db.add(Word(front=front, back=back, cefr_level=level))
            added += 1
    if added:
        db.commit()
    return added


def ensure_admin(db: Session) -> None:
    """Создать первого администратора из переменных окружения (если задан пароль)."""
    if not ADMIN_PASSWORD:
        return
    exists = db.query(User).filter(User.name == ADMIN_NAME).first()
    if exists:
        return
    db.add(
        User(
            name=ADMIN_NAME,
            password_hash=hash_password(ADMIN_PASSWORD),
            cefr_level="C2",
            is_admin=True,
        )
    )
    db.commit()


def generate_cards_for_user(db: Session, user: User, count: int = INITIAL_CARDS) -> int:
    """Выдать ученику новые карточки его уровня (и ниже), которых у него ещё нет."""
    # Уровни: свой и все, что проще — чтобы новичку было из чего набрать.
    try:
        idx = CEFR_ORDER.index((user.cefr_level or "A1").upper())
    except ValueError:
        idx = 0
    allowed_levels = CEFR_ORDER[: idx + 1]

    have_fronts = {
        c.front for c in db.query(Card).filter(Card.user_id == user.id).all()
    }

    pool = (
        db.query(Word)
        .filter(Word.cefr_level.in_(allowed_levels))
        .all()
    )
    candidates = [w for w in pool if w.front not in have_fronts]
    random.shuffle(candidates)

    created = 0
    for word in candidates[:count]:
        fsrs_json, due = new_card_state()
        db.add(
            Card(
                user_id=user.id,
                word_id=word.id,
                grammar_topic_id=word.grammar_topic_id,
                front=word.front,
                back=word.back,
                fsrs_json=fsrs_json,
                due=due,
                state=0,
                reps=0,
            )
        )
        created += 1
    if created:
        db.commit()
    return created


def add_words_for_user(db: Session, user: User, raw_text: str) -> int:
    """Массовый ввод слов из уроков EnglishDom.

    Принимает текст, по строке на слово в формате `слово | перевод`
    (разделитель | или таб). Создаёт слово в каталоге (уровень ученика),
    если его ещё нет, и сразу карточку этому ученику. Возвращает число добавленных.
    """
    have_fronts = {
        c.front.lower() for c in db.query(Card).filter(Card.user_id == user.id).all()
    }
    level = (user.cefr_level or "A1").upper()
    created = 0

    for raw in raw_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if "|" in line:
            front, _, back = line.partition("|")
        elif "\t" in line:
            front, _, back = line.partition("\t")
        elif " - " in line:
            front, _, back = line.partition(" - ")
        else:
            continue
        front, back = front.strip(), back.strip()
        if not front or not back or front.lower() in have_fronts:
            continue

        word = (
            db.query(Word)
            .filter(Word.front == front, Word.cefr_level == level)
            .first()
        )
        if not word:
            word = Word(front=front, back=back, cefr_level=level)
            db.add(word)
            db.flush()  # получить word.id

        fsrs_json, due = new_card_state()
        db.add(
            Card(
                user_id=user.id,
                word_id=word.id,
                grammar_topic_id=word.grammar_topic_id,
                front=front,
                back=back,
                fsrs_json=fsrs_json,
                due=due,
                state=0,
                reps=0,
            )
        )
        have_fronts.add(front.lower())
        created += 1

    if created:
        db.commit()
    return created
