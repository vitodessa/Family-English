"""Грамматика: теория под уровень + клоуз-упражнения (Claude).

Теория кэшируется (GrammarLesson), практика генерируется на лету.
"""

import json
from typing import Any

import httpx

from app.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, ANTHROPIC_MODEL_CHEAP

LEVEL_BRIEF = {
    "A1": "самыми простыми словами, очень коротко, минимум терминов",
    "A2": "простыми словами, коротко",
    "B1": "ясно, с парой нюансов",
    "B2": "подробнее, с типичными исключениями",
    "C1": "глубоко, с тонкостями употребления",
    "C2": "исчерпывающе, с нюансами и стилистикой",
}


def _call(system: str, user: str, max_tokens: int, model: str) -> str:
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={"model": model, "max_tokens": max_tokens,
              "system": system, "messages": [{"role": "user", "content": user}]},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return "".join(
        b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
    )


def _extract_json(raw: str) -> Any:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
    # берём от первой [ или { до последней ] или }
    starts = [i for i in (text.find("["), text.find("{")) if i != -1]
    if starts:
        start = min(starts)
        end = max(text.rfind("]"), text.rfind("}"))
        text = text[start:end + 1]
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def generate_theory(topic_name: str, level: str) -> str:
    """Короткая теория по теме под уровень — по-русски, с английскими примерами."""
    level = (level or "A1").upper()
    brief = LEVEL_BRIEF.get(level, LEVEL_BRIEF["A1"])
    system = ("Ты объясняешь английскую грамматику ученику ПО-РУССКИ: понятно, дружелюбно, "
              "без воды и без markdown-заголовков. Примеры — на английском с переводом.")
    user = (
        f"Объясни тему «{topic_name}» для уровня CEFR {level} — {brief}.\n"
        "Структура (просто абзацами): когда используется; как строится; "
        "2–3 примера на английском с переводом на русский. Коротко."
    )
    return _call(system, user, 700, ANTHROPIC_MODEL).strip()


def generate_cloze(topic_name: str, level: str, n: int = 5) -> list[dict[str, str]]:
    """Набор клоуз-упражнений («впиши правильную форму») по теме под уровень."""
    level = (level or "A1").upper()
    system = ("You create fill-in-the-blank English grammar exercises for learners. "
              "Match the CEFR level. Keep sentences natural and short.")
    user = (
        f'Create {n} fill-in-the-blank sentences to practice "{topic_name}" for a CEFR {level} learner.\n'
        'Each item: an English sentence with exactly ONE blank written as ___ , the correct word or form '
        'for that blank, and a short hint (base form of the verb, or a Russian cue).\n'
        'Return a SINGLE raw JSON array and nothing else:\n'
        '[{"sentence":"She ___ to school every day.","answer":"goes","hint":"go"}]'
    )
    data = _extract_json(_call(system, user, 900, ANTHROPIC_MODEL_CHEAP))
    if not isinstance(data, list):
        return []
    out = []
    for it in data:
        if not isinstance(it, dict):
            continue
        sentence = str(it.get("sentence", "")).strip()
        answer = str(it.get("answer", "")).strip()
        if "___" not in sentence or not answer:
            continue
        out.append({
            "sentence": sentence,
            "answer": answer,
            "hint": str(it.get("hint", "")).strip(),
        })
    return out[:n]
