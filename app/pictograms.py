"""Пиктограммы к словам (ARASAAC) — офлайн, без ключа в рантайме.

Карта «слово → id пиктограммы» лежит в app/pictograms_map.json (собрана разово).
Картинки кэшируются локально в data/pics (том с данными на проде). Если картинки
ещё нет в кэше — один раз тянем с ARASAAC и сохраняем; дальше отдаём с диска.
"""
import json
import os

import httpx

from app.config import BASE_DIR

MAP_PATH = BASE_DIR / "app" / "pictograms_map.json"
# Кэш картинок — в томе данных (рядом с family.db), переживает пересборку образа.
PICS_DIR = BASE_DIR / "data" / "pics"
ARASAAC_URL = "https://static.arasaac.org/pictograms/%s/%s_300.png"

_MAP = {}
if MAP_PATH.exists():
    try:
        _MAP = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    except Exception:
        _MAP = {}


def pictogram_id(word):
    """id пиктограммы для слова или None."""
    return _MAP.get((word or "").strip().lower())


def has_pictogram(word) -> bool:
    return pictogram_id(word) is not None


def local_path(pid):
    """Путь к картинке в кэше (может ещё не существовать)."""
    return PICS_DIR / ("%s.png" % pid)


def ensure_cached(pid):
    """Вернуть путь к картинке, при отсутствии — скачать с ARASAAC. None при неудаче."""
    p = local_path(pid)
    if p.exists() and p.stat().st_size > 0:
        return p
    try:
        PICS_DIR.mkdir(parents=True, exist_ok=True)
        r = httpx.get(ARASAAC_URL % (pid, pid), timeout=20,
                      headers={"User-Agent": "family-english/1.0"})
        r.raise_for_status()
        tmp = p.with_suffix(".tmp")
        tmp.write_bytes(r.content)
        os.replace(tmp, p)
        return p
    except Exception:
        return None


def coverage() -> int:
    return len(_MAP)
