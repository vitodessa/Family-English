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
    # семья и люди
    "mother": "👩", "father": "👨", "sister": "👧", "brother": "👦", "baby": "👶",
    "boy": "👦", "girl": "👧", "man": "👨", "woman": "👩", "child": "🧒", "people": "👥",
    # цвета
    "red": "🔴", "blue": "🔵", "green": "🟢", "yellow": "🟡", "black": "⚫",
    "white": "⚪", "brown": "🟤",
    # природа
    "sun": "☀️", "moon": "🌙", "star": "⭐", "sky": "☁️", "tree": "🌳", "flower": "🌸",
    "rain": "🌧️", "snow": "❄️", "wind": "💨", "sea": "🌊", "river": "🏞️",
    "mountain": "⛰️", "fire": "🔥",
    # еда
    "bread": "🍞", "milk": "🥛", "egg": "🥚", "apple": "🍎", "meat": "🥩", "fish": "🐟",
    "tea": "🍵", "coffee": "☕", "sugar": "🍬", "salt": "🧂", "fruit": "🍓",
    "soup": "🍲", "cake": "🍰",
    # животные
    "bird": "🐦", "cow": "🐄", "horse": "🐴", "pig": "🐷", "sheep": "🐑",
    "chicken": "🐔", "rabbit": "🐰",
    # дом и вещи
    "bed": "🛏️", "chair": "🪑", "key": "🔑", "phone": "📱", "clock": "🕐", "cup": "☕",
    "plate": "🍽️", "heart": "❤️", "ball": "⚽", "toy": "🧸", "gift": "🎁",
    # места и транспорт
    "train": "🚂", "bus": "🚌", "plane": "✈️", "bike": "🚲", "shop": "🏪",
    "street": "🛣️", "park": "🌳", "garden": "🌷", "music": "🎵", "game": "🎮",
    # время года
    "spring": "🌷", "summer": "🏖️", "autumn": "🍂", "winter": "⛄",
    # тело
    "face": "🙂", "hair": "💇", "ear": "👂", "nose": "👃", "mouth": "👄",
    "tooth": "🦷", "leg": "🦵", "finger": "👆",
}


def emoji_for(word: str) -> str:
    """Эмодзи для слова или пустая строка, если подходящего нет."""
    return WORD_EMOJI.get((word or "").strip().lower(), "")
