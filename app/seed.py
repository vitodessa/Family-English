"""Наполнение каталога слов и подбор карточек ученику."""

from sqlalchemy.orm import Session

from app.config import (
    ADMIN_NAME,
    ADMIN_PASSWORD,
    BASE_DIR,
    CEFR_ORDER,
    DECK_LOW_WATER,
    START_CARDS,
    TOPUP_CARDS,
    WARMUP_CARDS,
)
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


def _level_index(level) -> int:
    """Порядковый номер уровня CEFR (A1=0 … C2=5). Неизвестный уровень → 0."""
    try:
        return CEFR_ORDER.index((level or "A1").upper())
    except ValueError:
        return 0


def _ordered_words(db: Session) -> list[Word]:
    """Весь каталог «простое → сложное»: по уровню CEFR, внутри уровня — в порядке файла (по id)."""
    words = db.query(Word).all()
    words.sort(key=lambda w: (_level_index(w.cefr_level), w.id))
    return words


def learning_sequence(db: Session, user: User) -> list[Word]:
    """Индивидуальная последовательность подачи слов для ученика (простое → сложнее).

    Новичок (A1) идёт с самого начала каталога. Для уровня выше — сперва немного
    простых слов A1 «на разогрев», затем слова своего уровня и выше; промежуточные
    уровни пропускаем (старт от уровня, а не «всё ниже вперемешку»).
    """
    pool = _ordered_words(db)
    idx = _level_index(user.cefr_level)
    if idx == 0:
        seq = pool
    else:
        warmup = [w for w in pool if _level_index(w.cefr_level) == 0][:WARMUP_CARDS]
        own_and_up = [w for w in pool if _level_index(w.cefr_level) >= idx]
        seq = warmup + own_and_up

    # дедуп по front, порядок сохраняем
    seen, out = set(), []
    for w in seq:
        key = w.front.lower()
        if key not in seen:
            seen.add(key)
            out.append(w)
    return out


def _add_cards_from_sequence(db: Session, user: User, sequence: list[Word], count: int) -> int:
    """Добавить ученику до `count` следующих слов из последовательности, которых у него ещё нет."""
    have = {c.front.lower() for c in db.query(Card).filter(Card.user_id == user.id).all()}
    created = 0
    for w in sequence:
        if created >= count:
            break
        if w.front.lower() in have:
            continue
        fsrs_json, due = new_card_state()
        db.add(Card(
            user_id=user.id, word_id=w.id, grammar_topic_id=w.grammar_topic_id,
            front=w.front, back=w.back, fsrs_json=fsrs_json, due=due, state=0, reps=0,
        ))
        have.add(w.front.lower())
        created += 1
    if created:
        db.commit()
    return created


def generate_cards_for_user(db: Session, user: User) -> int:
    """Стартовая колода: первые простейшие слова от уровня ученика."""
    return _add_cards_from_sequence(db, user, learning_sequence(db, user), START_CARDS)


def top_up_deck(db: Session, user: User) -> int:
    """Долив «по мере изучения»: если свежих карточек (New/Learning) мало — добавить следующую порцию.

    Зовётся при заходе в кабинет/учёбу. Пока ученик разбирается со свежими словами,
    ничего не добавляем; как только он их освоил (перешли в Review) — подаём следующие.
    """
    fresh = (db.query(Card)
             .filter(Card.user_id == user.id, Card.state.in_([0, 1]))
             .count())
    if fresh >= DECK_LOW_WATER:
        return 0
    return _add_cards_from_sequence(db, user, learning_sequence(db, user), TOPUP_CARDS)


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
