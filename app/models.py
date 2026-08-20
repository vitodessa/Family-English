"""Ядро данных платформы: пользователи, слова, карточки, события обучения."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)  # имя = логин
    password_hash = Column(String, nullable=False)
    cefr_level = Column(String, default="A1")
    is_admin = Column(Boolean, default=False)
    daily_goal = Column(Integer, default=20)
    created_at = Column(DateTime, default=datetime.utcnow)


class GrammarTopic(Base):
    """Сквозной грамматический слой (не отдельный модуль).

    События обучения тегируются темами; дашборд грамматики «вырастает сам»
    из накопленных тегов. Закладывается с первого дня (см. PRODUCT_SPEC).
    """

    __tablename__ = "grammar_topics"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    cefr_level = Column(String, index=True)  # уровень пункта в CEFR-лесенке
    description = Column(Text)


class Word(Base):
    """Общий каталог слов. Наполняется из app/vocabulary/*.txt и вводом из уроков."""

    __tablename__ = "words"

    id = Column(Integer, primary_key=True)
    front = Column(String, nullable=False)  # английское слово
    back = Column(String, nullable=False)   # перевод
    cefr_level = Column(String, index=True)
    grammar_topic_id = Column(Integer, ForeignKey("grammar_topics.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Card(Base):
    """Карточка конкретного ученика. Состояние FSRS хранится в fsrs_json."""

    __tablename__ = "cards"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    word_id = Column(Integer, ForeignKey("words.id"), nullable=True)
    grammar_topic_id = Column(Integer, ForeignKey("grammar_topics.id"), nullable=True)
    front = Column(String, nullable=False)
    back = Column(String, nullable=False)

    # Полное состояние планировщика FSRS (источник правды), сериализованное в JSON.
    fsrs_json = Column(Text, nullable=False)
    # Денормализовано для быстрых запросов и отображения:
    due = Column(DateTime, index=True)
    state = Column(Integer, default=0)  # 0 New / 1 Learning / 2 Review / 3 Relearning
    reps = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)


class LearningEvent(Base):
    """Некорректируемый журнал событий обучения (append-only).

    Каждое повторение = одна строка. Не обновляем и не удаляем — основа для
    дашборда, который «растёт сам».
    """

    __tablename__ = "learning_events"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    card_id = Column(Integer, ForeignKey("cards.id"), nullable=False)
    grammar_topic_id = Column(Integer, ForeignKey("grammar_topics.id"), nullable=True)
    rating = Column(Integer, nullable=False)  # 1 Again / 2 Hard / 3 Good / 4 Easy
    state_after = Column(Integer)
    elapsed_days = Column(Integer)
    scheduled_days = Column(Integer)
    reviewed_at = Column(DateTime, default=datetime.utcnow, index=True)


class Session(Base):
    """Сеанс любого модуля (общая модель). Speaking — первый, кто пишет сюда."""

    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    module = Column(String, default="speaking")
    topic = Column(String, default="")
    summary = Column(Text, default="")
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)


class Mistake(Base):
    """Ошибка ученика с категорией. Появляется со Speaking/Writing (см. PRODUCT_SPEC)."""

    __tablename__ = "mistakes"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=True)
    grammar_topic_id = Column(Integer, ForeignKey("grammar_topics.id"), nullable=True)
    original = Column(Text, nullable=False)
    correction = Column(Text, nullable=False)
    explanation = Column(Text, default="")
    category = Column(String, index=True)  # grammar/tense/articles/prepositions/...
    source_module = Column(String, default="speaking")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class GrammarLesson(Base):
    """Теория по грамматической теме под уровень (генерируется AI, кэшируется).

    Практика (клоуз-упражнения) генерируется на лету; ошибки пишутся в Mistake
    с grammar_topic_id — так «сам вырастает» грамматический дашборд.
    """

    __tablename__ = "grammar_lessons"

    id = Column(Integer, primary_key=True)
    grammar_topic_id = Column(Integer, ForeignKey("grammar_topics.id"), nullable=False, index=True)
    cefr_level = Column(String, index=True)
    theory = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class ContentItem(Base):
    """Текст для чтения. В v1 генерируется AI под уровень; читается с тап-переводом.

    Часть «единой памяти»: слово, тапнутое при чтении, уходит в каталог и карточки.
    """

    __tablename__ = "content_items"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    cefr_level = Column(String, index=True)
    topic = Column(String, default="")
    # Глоссарий всех слов текста {слово: перевод} (JSON) — строится один раз,
    # чтобы наведение в ридере было мгновенным, без вызова AI на каждое слово.
    glossary = Column(Text, default="")
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
