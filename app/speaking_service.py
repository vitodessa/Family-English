"""Speaking: мозг (Claude) + голос (ElevenLabs) + запись в «единую память».

Claude получает методичку (кэшируется) + контекст ученика и возвращает СТРОГО JSON:
{ "reply": "...", "mistakes": [...], "new_vocab": [...] }
— reply озвучивается, ошибки и новые слова тихо сохраняются (новые слова → карточки).
"""

import json
from typing import Any

import httpx
from sqlalchemy.orm import Session as DBSession

from app.config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    ELEVENLABS_API_KEY,
    ELEVENLABS_MODEL,
    ELEVENLABS_VOICE_ID,
)
from app.fsrs_service import new_card_state
from app.models import Card, Mistake, User, Word

# Длинная неизменная методичка — помечается для кэширования (−90% на повторе).
STATIC_TUTOR_INSTRUCTIONS = """You are a warm, patient personal English tutor for a family. \
You talk to one student at a time through a VOICE interface in a live back-and-forth call, so your `reply` is read aloud — keep it SHORT: 1–3 simple sentences, natural, no markdown, no emoji. End with a short question so the student keeps talking.

How you handle each student turn — do three things at once:
1. RESPOND naturally to keep the conversation alive. Ask a follow-up question so the student keeps talking.
2. CORRECT mistakes WITHOUT breaking the flow: record them in the structured field; in speech you may gently recast the correct form, never lecture.
3. INTRODUCE 1–2 useful new words/phrases when natural, and record them.

ADAPTIVITY IS YOUR MOST IMPORTANT RULE:
- Match the student's REAL level shown by how they actually speak right now, not just the label. If they speak in short simple sentences, you do the same.
- Start a little SIMPLER than the target level; raise difficulty only when they clearly cope.
- Prefer everyday topics (family, food, weekend, plans, work). Avoid abstract or philosophical topics unless the student raises them.
- Use common, high-frequency words. If the student hesitates, goes quiet, or makes many mistakes, slow down, simplify, and give a quick Russian hint.
Do not log trivial typos as mistakes — only real learning opportunities.

Mistake `category` is one of: grammar, tense, articles, prepositions, word_order, vocab, pronunciation, other.

OUTPUT — ABSOLUTELY CRITICAL: respond with a SINGLE raw JSON object and nothing else (no markdown fences):
{
  "reply": "spoken reply, 2-4 sentences, plain English",
  "mistakes": [{"original":"...","correction":"...","explanation":"кратко по-русски","category":"tense"}],
  "new_vocab": [{"word":"to commute","translation":"ездить на работу","example":"I commute to work by bike."}]
}
Empty arrays if none. Never omit the keys."""


def build_context(user: User, recent_mistakes: list[Mistake], due_words: list[Card],
                  topic: str = "", level: str = "") -> str:
    eff_level = (level or user.cefr_level or "A1").upper()
    parts = [
        "# Current student",
        f"- Name: {user.name}",
        f"- Target level (ceiling): {eff_level} — calibrate DOWN to match how the student actually speaks",
    ]
    if topic:
        parts.append(f"\n# Today's topic\n{topic}")
    if recent_mistakes:
        parts.append("\n# Recent recurring mistakes (revisit gently)")
        for m in recent_mistakes[:8]:
            parts.append(f'- [{m.category}] "{m.original}" → "{m.correction}"')
    if due_words:
        parts.append("\n# Words to weave in naturally if you can")
        for c in due_words[:10]:
            parts.append(f"- {c.front} — {c.back}")
    parts.append(
        "\n# Continue the lesson. If this is the first message, greet the student by name "
        "and propose a topic. Respond with raw JSON only."
    )
    return "\n".join(parts)


def _call_claude(dynamic_context: str, history: list[dict[str, Any]]) -> str:
    system = [
        {"type": "text", "text": STATIC_TUTOR_INSTRUCTIONS,
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
        json={"model": ANTHROPIC_MODEL, "max_tokens": 700,
              "system": system, "messages": history},
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
        return {"reply": raw.strip(), "mistakes": [], "new_vocab": []}
    obj.setdefault("reply", "")
    obj.setdefault("mistakes", [])
    obj.setdefault("new_vocab", [])
    return obj


def _save_turn(db: DBSession, user: User, session_id: int, parsed: dict[str, Any]) -> None:
    # Ошибки → журнал ошибок
    for m in parsed.get("mistakes", []):
        if not m.get("original") or not m.get("correction"):
            continue
        db.add(Mistake(
            user_id=user.id, session_id=session_id,
            original=str(m.get("original"))[:1000],
            correction=str(m.get("correction"))[:1000],
            explanation=str(m.get("explanation", ""))[:1000],
            category=str(m.get("category", "other"))[:40],
            source_module="speaking",
        ))

    # Новые слова → каталог + карточки этому ученику (вот «единая память»)
    have = {c.front.lower() for c in db.query(Card).filter(Card.user_id == user.id).all()}
    level = (user.cefr_level or "A1").upper()
    for v in parsed.get("new_vocab", []):
        front = str(v.get("word", "")).strip()
        back = str(v.get("translation", "")).strip()
        if not front or not back or front.lower() in have:
            continue
        word = (db.query(Word)
                .filter(Word.front == front, Word.cefr_level == level).first())
        if not word:
            word = Word(front=front, back=back, cefr_level=level)
            db.add(word)
            db.flush()
        fsrs_json, due = new_card_state()
        db.add(Card(user_id=user.id, word_id=word.id, grammar_topic_id=word.grammar_topic_id,
                    front=front, back=back, fsrs_json=fsrs_json, due=due, state=0, reps=0))
        have.add(front.lower())

    db.commit()


def chat_turn(db: DBSession, user: User, session_id: int,
              history: list[dict[str, Any]], topic: str = "",
              level: str = "") -> dict[str, Any]:
    """history — список реплик [{role, content}], последняя — реплика ученика."""
    recent = (db.query(Mistake).filter(Mistake.user_id == user.id)
              .order_by(Mistake.created_at.desc()).limit(8).all())
    from datetime import datetime
    due = (db.query(Card)
           .filter(Card.user_id == user.id, Card.due <= datetime.utcnow())
           .order_by(Card.due.asc()).limit(10).all())

    raw = _call_claude(build_context(user, recent, due, topic, level), history)
    parsed = _parse(raw)
    _save_turn(db, user, session_id, parsed)
    return parsed


def text_to_speech(text: str, speed: float = 1.0) -> bytes:
    """Озвучка реплики натуральным голосом (ElevenLabs). Возвращает mp3-байты.

    speed — скорость речи (0.7 медленно … 1.2 быстро), ElevenLabs ограничивает диапазон.
    """
    speed = max(0.7, min(1.2, float(speed)))
    resp = httpx.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}",
        params={"output_format": "mp3_44100_128"},
        headers={"xi-api-key": ELEVENLABS_API_KEY, "content-type": "application/json"},
        json={"text": text, "model_id": ELEVENLABS_MODEL,
              "voice_settings": {"stability": 0.4, "similarity_boost": 0.7, "speed": speed}},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.content
