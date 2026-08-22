"""Аудирование: генерация короткого скрипта под уровень + пропуски для gap-fill.

Claude пишет монолог и выбирает ключевые слова; сервер строит клоуз (пропуски)
из полного текста и списка слов — надёжно, без рассинхрона. Озвучка — ElevenLabs.
"""

import json
import re
from typing import Any

from app import ai_http
from app.config import ANTHROPIC_MODEL

LEVEL_BRIEF = {
    "A1": ("very simple spoken English, short present-tense sentences, about 40 words", 4),
    "A2": ("simple everyday spoken English, about 60 words", 5),
    "B1": ("clear spoken English, about 90 words", 6),
    "B2": ("natural spoken English with some richer vocabulary, about 120 words", 7),
    "C1": ("fluent, nuanced spoken English, about 150 words", 8),
    "C2": ("sophisticated spoken English, about 170 words", 8),
}


def _call(system: str, user: str, max_tokens: int) -> str:
    payload = {"model": ANTHROPIC_MODEL, "max_tokens": max_tokens,
               "system": system, "messages": [{"role": "user", "content": user}]}
    return ai_http.messages_text(payload)


def _parse_json(raw: str) -> dict[str, Any]:
    return ai_http.extract_json(raw) or {}


def _build_cloze(full: str, answers: list[str]) -> tuple[str, list[str]]:
    """Заменить первое вхождение каждого слова-ответа на ___. Возвращает (клоуз, реально пропущенные)."""
    cloze = full
    used = []
    for a in answers:
        a = (a or "").strip()
        if not a:
            continue
        pat = re.compile(r"\b" + re.escape(a) + r"\b", re.IGNORECASE)
        m = pat.search(cloze)
        if m:
            cloze = cloze[:m.start()] + "___" + cloze[m.end():]
            used.append(a)
    return cloze, used


def pick_blanks(text: str, level: str, n=None) -> list[str]:
    """Выбрать ключевые слова текста для пропусков (для готового транскрипта — напр. видео)."""
    level = (level or "A1").upper()
    if n is None:
        n = LEVEL_BRIEF.get(level, LEVEL_BRIEF["A1"])[1]
    system = ("You select key content words from an English text to blank out for a listening "
              "gap-fill. Choose nouns/verbs/adjectives, never 'the/a/is'.")
    user = (
        f"From the text below, choose {n} KEY content words suitable to blank out for a CEFR "
        f"{level} learner. Return a SINGLE raw JSON array of the chosen words (lowercase), "
        "in order of appearance, nothing else:\n"
        '["word1","word2",...]\n\nText:\n' + text[:3000]
    )
    raw = _call(system, user, max_tokens=300).strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw[raw.find("["):raw.rfind("]") + 1]
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return []
    return [str(w).strip() for w in data if str(w).strip()] if isinstance(data, list) else []


def generate_listening(level: str, topic: str) -> dict[str, Any]:
    """Сгенерировать аудио-скрипт. Возвращает {title, full, cloze, answers}."""
    level = (level or "A1").upper()
    brief, n = LEVEL_BRIEF.get(level, LEVEL_BRIEF["A1"])
    topic = (topic or "").strip() or "everyday life"
    system = ("You write short English LISTENING scripts (spoken monologue) for learners. "
              "Match the CEFR level exactly. Natural to say aloud.")
    user = (
        f"Write a short spoken English monologue for a CEFR {level} learner about: {topic}.\n"
        f"Constraints: {brief}. Give it a short title.\n"
        f"Then choose {n} KEY content words from the text (nouns/verbs/adjectives — never the/a/is) "
        "to blank out for a listening gap-fill.\n"
        'Return a SINGLE raw JSON object and nothing else: '
        '{"title":"...","full":"the complete spoken text","answers":["word1","word2",...]}'
    )
    obj = _parse_json(_call(system, user, max_tokens=700))
    title = str(obj.get("title") or "Listening").strip()[:120]
    full = str(obj.get("full") or "").strip()
    answers = [str(a).strip() for a in obj.get("answers", []) if str(a).strip()]
    cloze, used = _build_cloze(full, answers)
    return {"title": title, "full": full, "cloze": cloze, "answers": used}
