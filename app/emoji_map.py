"""Эмодзи-иллюстрации к словам — «картинки» карточек (как в EnglishDom).

Только очевидные конкретные слова; для абстрактных эмодзи не показываем.
Ключ — английское слово (в нижнем регистре). Нет ключа → карточка без картинки.
"""

WORD_EMOJI = {
    # A1 — конкретика
    "house": "🏠", "water": "💧", "food": "🍽️", "friend": "👫",
    "family": "👨‍👩‍👧‍👦", "school": "🏫", "book": "📖", "dog": "🐶",
    "cat": "🐱", "car": "🚗", "city": "🏙️", "day": "☀️", "night": "🌙",
    "morning": "🌅", "time": "⏰", "year": "📅", "week": "🗓️", "hand": "✋",
    "eye": "👁️", "door": "🚪", "window": "🪟", "money": "💰", "good": "👍",
    "bad": "👎", "happy": "😊", "hot": "🔥", "cold": "❄️", "old": "👴",
    "fast": "⚡", "slow": "🐢", "eat": "🍴", "drink": "🥤", "sleep": "😴",
    "read": "📚", "write": "✍️", "speak": "🗣️", "listen": "👂", "work": "💼",
    "play": "🎮", "run": "🏃", "walk": "🚶", "see": "👀", "buy": "🛒",
    "love": "❤️", "help": "🆘", "give": "🎁",
    # A2 / путешествия
    "research": "🔬", "technology": "💻", "temperature": "🌡️",
    "transportation": "🚌", "university": "🎓", "vacation": "🏖️",
    "weather": "🌤️", "website": "🌐", "travel": "✈️", "remember": "🧠",
    "arrive": "🛬", "journey": "🧳", "country": "🗺️", "airport": "🛫",
    "hotel": "🏨", "ticket": "🎫",
}


def emoji_for(word: str) -> str:
    """Эмодзи для слова или пустая строка, если подходящего нет."""
    return WORD_EMOJI.get((word or "").strip().lower(), "")
