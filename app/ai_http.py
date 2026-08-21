"""Единая точка вызова Anthropic Messages API с ретраями.

У API бывают временные сбои (перегруз, 429/5xx, разовый 400 на корректном
запросе, обрыв сети). Раньше любой такой сбой всплывал ошибкой на странице
ученику. Здесь — общий POST с несколькими попытками и экспоненциальной паузой;
сервисы (writing/listening/speaking) шлют готовый payload и получают текст.
"""

import time

import httpx

from app.config import ANTHROPIC_API_KEY

_URL = "https://api.anthropic.com/v1/messages"
_HEADERS = {
    "x-api-key": ANTHROPIC_API_KEY,
    "anthropic-version": "2023-06-01",
    "content-type": "application/json",
}
# Временные статусы — повторяем. 400 включён намеренно: наблюдался разовый 400
# на корректном запросе к api.anthropic.com.
_RETRY_STATUS = {400, 408, 409, 429, 500, 502, 503, 504, 529}


def post_messages(payload: dict, timeout: float = 60, attempts: int = 3) -> httpx.Response:
    """POST в Messages API с ретраями. Возвращает успешный Response или бросает."""
    delay = 1.0
    last_exc = None
    resp = None
    for attempt in range(attempts):
        try:
            resp = httpx.post(_URL, headers=_HEADERS, json=payload, timeout=timeout)
            if resp.status_code in _RETRY_STATUS and attempt < attempts - 1:
                time.sleep(delay)
                delay *= 1.8
                continue
            resp.raise_for_status()
            return resp
        except httpx.RequestError as e:  # сеть/таймаут
            last_exc = e
            if attempt < attempts - 1:
                time.sleep(delay)
                delay *= 1.8
                continue
            raise
    # исчерпали попытки на retryable-статусе — поднять как ошибку статуса
    if resp is not None:
        resp.raise_for_status()
    if last_exc:
        raise last_exc
    raise RuntimeError("post_messages: no response")


def messages_text(payload: dict, timeout: float = 60) -> str:
    """Как post_messages, но сразу склеивает текстовые блоки ответа в строку."""
    data = post_messages(payload, timeout=timeout).json()
    return "".join(
        b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
    )
