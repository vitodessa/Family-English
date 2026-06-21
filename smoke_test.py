"""Дымовой тест: проверяет основные сценарии против живого сервера.

Запуск:  python smoke_test.py http://localhost:8090
"""

import sys
import uuid

import httpx


def main(base: str) -> int:
    name = "smoke_" + uuid.uuid4().hex[:8]
    password = "test12345"

    with httpx.Client(base_url=base, follow_redirects=True, timeout=15) as c:
        assert c.get("/healthz").json()["status"] == "ok", "healthz"

        # регистрация -> попадаем в кабинет
        r = c.post("/register", data={"name": name, "password": password, "cefr_level": "A2"})
        assert "Кабинет" in r.text or "Привет" in r.text, "register -> dashboard"

        # карточки выданы, есть что учить
        r = c.get("/study")
        assert "Показать ответ" in r.text, "study has a due card"

        # достаём id первой карточки и оцениваем её
        import re
        m = re.search(r'name="card_id" value="(\d+)"', r.text)
        assert m, "card_id present"
        card_id = m.group(1)
        r = c.post("/review", data={"card_id": card_id, "rating": "3"})
        assert r.status_code == 200, "review accepted"

        # выход и повторный вход
        c.get("/logout")
        r = c.post("/login", data={"name": name, "password": password})
        assert "Привет" in r.text, "login works after logout"

        # чужой профиль/карточку оценить нельзя — но это уже проверяет код (RBAC)
        print(f"OK ✓  все проверки прошли (пользователь {name})")
        return 0


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8090"
    sys.exit(main(base))
