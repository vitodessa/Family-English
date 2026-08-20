"""Чтение: генерация текста под уровень (Claude) + перевод слова в контексте.

Тексты пишутся под CEFR-уровень ученика; перевод слова — дешёвой моделью,
с учётом предложения, в котором слово встретилось.
"""

import json
import re
from typing import Any

import httpx

from app.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, ANTHROPIC_MODEL_CHEAP

# Краткое ТЗ под каждый уровень — чем ниже, тем короче и проще.
LEVEL_BRIEF = {
    "A1": "very simple, short present-tense sentences, only the most common words, about 50 words",
    "A2": "simple everyday sentences and vocabulary, about 80 words",
    "B1": "clear short paragraphs, common vocabulary, about 120 words",
    "B2": "richer vocabulary and some complex sentences, about 150 words",
    "C1": "advanced vocabulary and varied structures, about 180 words",
    "C2": "sophisticated, nuanced language, about 200 words",
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


def _parse_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):text.rfind("}") + 1]
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return {}


def generate_text(level: str, topic: str) -> tuple[str, str]:
    """Сгенерировать короткий текст под уровень. Возвращает (заголовок, тело)."""
    level = (level or "A1").upper()
    brief = LEVEL_BRIEF.get(level, LEVEL_BRIEF["A1"])
    topic = (topic or "").strip() or "everyday life"
    system = ("You write short, engaging English reading texts for language learners. "
              "Match the requested CEFR level exactly — vocabulary and grammar must fit it.")
    user = (
        f"Write an English reading text for a CEFR {level} learner about: {topic}.\n"
        f"Constraints: {brief}. Natural, coherent, with a short catchy title.\n"
        'Return a SINGLE raw JSON object and nothing else: {"title":"...","text":"..."}'
    )
    obj = _parse_json(_call(system, user, max_tokens=700, model=ANTHROPIC_MODEL))
    title = str(obj.get("title") or "Reading").strip()[:120]
    body = str(obj.get("text") or "").strip()
    return title, body


def _distinct_words(body: str, limit: int = 200) -> list[str]:
    """Уникальные слова текста в нижнем регистре, в порядке появления."""
    seen, out = set(), []
    for w in re.findall(r"[A-Za-z']+", body):
        lw = w.lower()
        if len(lw) > 1 and lw not in seen:
            seen.add(lw)
            out.append(lw)
    return out[:limit]


def build_glossary(body: str) -> dict[str, str]:
    """Перевести ВСЕ слова текста за один вызов. {слово(lower): перевод}.

    Строится один раз на текст → в ридере наведение мгновенное (без сети).
    """
    words = _distinct_words(body)
    if not words:
        return {}
    system = ("You are a bilingual dictionary. For each English word give a SHORT Russian "
              "translation (1-2 words) as used in the given text. Common function words too.")
    user = (
        "Text:\n" + body + "\n\n"
        "Translate EXACTLY these words. Return a SINGLE raw JSON object {word: russian}, "
        "keys lowercase, nothing else:\n" + ", ".join(words)
    )
    obj = _parse_json(_call(system, user, max_tokens=2000, model=ANTHROPIC_MODEL_CHEAP))
    return {
        str(k).strip().lower(): str(v).strip()
        for k, v in obj.items() if str(v).strip()
    }


def translate_word(word: str, sentence: str, level: str = "") -> str:
    """Перевести английское слово на русский в контексте предложения."""
    system = ("You are a precise bilingual dictionary. Translate ONE English word into Russian "
              "as used in the given sentence. Answer with ONLY the Russian translation "
              "(1-3 words), nothing else — no quotes, no English, no explanation.")
    user = f'Word: "{word}"\nSentence: "{sentence[:400]}"\nRussian translation:'
    raw = _call(system, user, max_tokens=24, model=ANTHROPIC_MODEL_CHEAP)
    return raw.strip().strip('"').splitlines()[0][:100] if raw.strip() else ""
