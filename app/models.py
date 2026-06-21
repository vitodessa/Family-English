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
