"""Письмо: задание под уровень + разбор написанного (Claude).

Та же архитектура, что Speaking, но текст: ученик пишет ответ на задание,
Claude возвращает отзыв + исправленную версию + ошибки + новые слова.
Ошибки и слова сохраняются в «единую память» (см. speaking_service._save_turn).
"""

import json
import random
from typing import Any

import httpx

from app.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL
from app.models import User

# Задания под уровень (курируемые; можно позже генерировать AI).
TASKS = {
    "A1": [
        "Напиши 2–3 простых предложения о своей семье.",
        "Напиши, что ты любишь есть. 2–3 предложения.",
        "Опиши свой день простыми словами (2–3 предложения).",
        "Напиши про своего друга. 2–3 предложения.",
        "Что ты делаешь утром? Напиши 2–3 предложения.",
    ],
    "A2": [
        "Напиши 4–5 предложений о том, как прошли твои выходные.",
        "Опиши свой любимый фильм или книгу (4–5 предложений).",
        "Напиши о своих планах на лето.",
        "Расскажи о своём городе (4–5 предложений).",
    ],
    "B1": [
        "Напиши небольшой текст (5–7 предложений) о том, как прошёл твой день.",
        "Опиши место, которое хотел бы посетить, и объясни почему.",
        "Напиши о хобби, которым увлекаешься, и что оно тебе даёт.",
    ],
    "B2": [
        "Напиши около 100 слов: плюсы и минусы удалённой работы.",
        "Опиши запомнившееся путешествие и чем оно тебя впечатлило.",
        "Согласен ли ты, что социальные сети сближают людей? Аргументируй.",
    ],
    "C1": [
        "Аргументированный абзац: делают ли технологии нас более одинокими?",
        "Опиши сложную ситуацию, с которой справился, и какие выводы сделал.",
    ],
    "C2": [
        "Развёрнутое рассуждение о роли искусства в обществе.",
        "Проанализируй утверждение: «Свобода без ответственности невозможна».",
    ],
}

STATIC_WRITING_INSTRUCTIONS = """You are a warm, patient personal English WRITING tutor for a family. \
A student was given a writing TASK and wrote a response. Review it kindly and usefully.

Do all of this at once:
1. Give SHORT encouraging feedback IN RUSSIAN: what is good, and the ONE main thing to improve. Warm, never a lecture.
2. Provide a CORRECTED version of their text in natural English AT THEIR LEVEL — keep their meaning and length, fix the errors, do NOT add new ideas or make it fancier than their level.
3. List concrete MISTAKES: the original fragment, the correction, a short Russian explanation, and a category.
4. When it fits the level, add 1–2 useful new words/phrases (skip entirely for true beginners).

Mistake `category` is one of: grammar, tense, articles, prepositions, word_order, vocab, spelling, punctuation, other.

OUTPUT — ABSOLUTELY CRITICAL: respond with a SINGLE raw JSON object and nothing else (no markdown fences):
{
  "feedback": "короткий тёплый отзыв по-русски: что хорошо и что улучшить",
  "corrected": "corrected English version of the student's text",
  "mistakes": [{"original":"...","correction":"...","explanation":"кратко по-русски","category":"tense"}],
  "new_vocab": [{"word":"...","translation":"...","example":"..."}]
}
Empty arrays if none. Never omit the keys."""


def get_task(level: str) -> str:
    pool = TASKS.get((level or "A1").upper()) or TASKS["A1"]
    return random.choice(pool)


def _build_context(user: User, level: str, task: str) -> str:
    eff = (level or user.cefr_level or "A1").upper()
    parts = [
        "# Student",
        f"- Name: {user.name}",
        f"- Level (HARD CEILING): {eff}",
        f"\n# Task given to the student\n{task}",
    ]
    if eff == "A1":
        parts.append(
            "\n# LEVEL MODE — TRUE BEGINNER (A1): expect just 2–3 very simple sentences. "
            "Be extra gentle; keep `corrected` in the simplest English; feedback short and simple; "
            "keep `new_vocab` empty."
        )
    elif eff == "A2":
        parts.append(
            "\n# LEVEL MODE — EASY (A2): keep `corrected` simple; at most ONE new easy word."
        )
    parts.append("\n# Review the student's writing below. Respond with raw JSON only.")
    return "\n".join(parts)


def _call_claude(dynamic_context: str, student_text: str, max_tokens: int) -> str:
    system = [
        {"type": "text", "text": STATIC_WRITING_INSTRUCTIONS,
         "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": dynamic_context},
    ]
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={"model": ANTHROPIC_MODEL, "max_tokens": max_tokens,
              "system": system, "messages": [{"role": "user", "content": student_text}]},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return "".join(
        b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
    )


def _parse(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):text.rfind("}") + 1]
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return {"feedback": "", "corrected": raw.strip(), "mistakes": [], "new_vocab": []}
    obj.setdefault("feedback", "")
    obj.setdefault("corrected", "")
    obj.setdefault("mistakes", [])
    obj.setdefault("new_vocab", [])
    return obj


def review(user: User, level: str, task: str, text: str) -> dict[str, Any]:
    """Разобрать написанное. Возвращает {feedback, corrected, mistakes, new_vocab}."""
    eff = (level or user.cefr_level or "A1").upper()
    max_tokens = 500 if eff == "A1" else 700 if eff == "A2" else 900
    raw = _call_claude(_build_context(user, eff, task), text[:4000], max_tokens)
    return _parse(raw)
