# Family English

Семейная платформа изучения английского. Ядро: пользователи, слова, карточки и
журнал обучения. Первый модуль — карточки с научным интервальным повторением
(**FSRS**).

Стек: Python · FastAPI · Jinja2 (серверный рендеринг) · SQLAlchemy · SQLite
(с прицелом на PostgreSQL) · пакет `fsrs`.

## Локальный запуск (без Docker)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # задать SECRET_KEY и (опц.) ADMIN_PASSWORD
uvicorn app.main:app --reload --port 8090
# открыть http://localhost:8090
```

Сгенерировать секрет: `python -c "import secrets; print(secrets.token_hex(32))"`

## Запуск в Docker (для сервера)

```bash
cp .env.example .env          # заполнить SECRET_KEY и ADMIN_PASSWORD
docker compose up -d --build
# http://localhost:8090 ; данные — в томе family_db (переживают пересборку)
```

## Дымовой тест

```bash
python smoke_test.py http://localhost:8090
```

## Что внутри

- `app/models.py` — ядро данных: `User`, `Word`, `Card`, `LearningEvent` (журнал append-only).
- `app/fsrs_service.py` — обёртка над настоящим планировщиком FSRS.
- `app/seed.py` — загрузка слов из `app/vocabulary/*.txt` и подбор карточек ученику.
- `app/routers/` — вход/регистрация, учёба, админка.
- Пароли хэшируются (bcrypt), сессии — в подписанной cookie. Секреты только в `.env`.

## Дальше по плану (модули поверх ядра)

Говорение · Чтение · Письмо · Грамматика — каждый встаёт на это же ядро.
Переход на PostgreSQL — сменой `DATABASE_URL`, без правки кода.
