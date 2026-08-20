# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**Family English** — a self-hosted English-learning web app for a single family (~4 users, not a SaaS). Server-rendered FastAPI + Jinja2, SQLAlchemy over SQLite (switchable to PostgreSQL). UI text, code comments, and commit messages are in **Russian** — match that when editing.

The product thesis (see [docs/PRODUCT_SPEC.md](docs/PRODUCT_SPEC.md)) is a **single shared learning memory**: a word encountered in any module flows into the FSRS card deck and later resurfaces in other modules (e.g. the speaking tutor weaves due words into conversation; words it introduces become new cards). When adding features, the question is usually "how does this read from / write to the shared core" — not "what new silo does this need."

## Commands

```bash
# Local dev
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                 # set SECRET_KEY, optionally ADMIN_PASSWORD + AI keys
uvicorn app.main:app --reload --port 8090

# Generate a SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"

# Docker (mirrors production)
docker compose up -d --build         # data persists in the family_db volume

# Smoke test against a running server (register → study → review → re-login)
python smoke_test.py http://localhost:8090
```

There is **no unit test suite and no linter configured.** `smoke_test.py` is the only test — it drives a live HTTP server end-to-end. CI ([.github/workflows/deploy.yml](.github/workflows/deploy.yml)) only verifies imports (`python -c "from app.main import app"`) before deploying; the smoke test runs on the server post-deploy, inside the container.

## Architecture

Entry point [app/main.py](app/main.py) wires routers and runs `Base.metadata.create_all` plus idempotent seeding (`ensure_grammar_topics`, `seed_words`, `ensure_admin`) in the lifespan handler. **There are no migrations yet** — schema changes happen by editing models and recreating; Alembic is a future addition, so destructive model changes against an existing `data/family.db` need manual care.

Layering:
- **[app/models.py](app/models.py)** — the entire data core in one file: `User`, `Word` (shared catalog), `Card` (per-user), `LearningEvent`, plus `GrammarTopic`, `Session`, `Mistake`. The latter three are seeded/used by later modules but defined up front by design.
- **[app/database.py](app/database.py)** / **[app/config.py](app/config.py)** — engine + `get_db` dependency; all config (secrets, `DATABASE_URL`, AI keys, `CEFR_ORDER`) reads from env/`.env`. Driver is chosen by `DATABASE_URL` prefix, so SQLite↔Postgres is a config change, not a code change.
- **[app/fsrs_service.py](app/fsrs_service.py)** — thin wrapper over the `fsrs` package. **All spaced-repetition logic lives here**; don't reimplement scheduling.
- **[app/seed.py](app/seed.py)** — loads vocab and builds per-user card decks.
- **[app/routers/](app/routers/)** — `auth`, `study` (dashboard + card review), `vocab` (`/my-words` bulk import), `speaking`, `admin`.
- **[app/speaking_service.py](app/speaking_service.py)** — the AI tutor: Claude for dialogue, ElevenLabs for voice.
- **[app/templating.py](app/templating.py)** — always render via `render(request, name, db=...)`, which injects `current_user` into the template context.

### Conventions that matter

- **FSRS state is the source of truth, stored as JSON** in `Card.fsrs_json`. The `due`, `state`, `reps` columns are **denormalized** copies for querying/display — they must be updated together via the dict returned by `apply_review` (see [study.py](app/routers/study.py)).
- **`LearningEvent` is append-only.** Each review writes one row; never update or delete them — the "self-growing" dashboards read from this log.
- **`grammar_topics` is a cross-cutting tag, not a module.** Words/cards/events carry `grammar_topic_id`; the grammar dashboard is meant to emerge from accumulated tags.
- **Authz is manual ownership filtering.** Every per-user query filters `.filter(... user_id == user.id)` (see `/review`, all speaking endpoints). Admin routes gate through `_require_admin`. There is no ORM-level row security — preserve these filters when touching queries.
- **Sessions are signed cookies** via `SessionMiddleware`; `user_id` in the session is the only auth token. `get_current_user` ([app/deps.py](app/deps.py)) resolves it. Passwords are bcrypt-hashed ([app/security.py](app/security.py)).
- **Vocab seed format**: `app/vocabulary/<level>.txt`, one `front|back` line per word; filename stem (e.g. `a1.txt`) becomes the CEFR level. Seeding is idempotent (dedupes on front+level). `generate_cards_for_user` gives a user words at their level **and below**.

### Speaking module specifics

`/speaking/*` endpoints are gated by `speaking_enabled()` — they return 503 unless **both** `ANTHROPIC_API_KEY` and `ELEVENLABS_API_KEY` are set. The frontend keeps conversation `history` client-side and posts it each turn.

`speaking_service.chat_turn` builds the prompt as a cached static system block (`STATIC_TUTOR_INSTRUCTIONS`, marked `cache_control: ephemeral`) plus a dynamic per-student context (recent mistakes + due words). Claude must return **a single raw JSON object** `{reply, mistakes, new_vocab}`; `_parse` tolerates stray markdown fences. `_save_turn` then writes mistakes to `Mistake` and **turns `new_vocab` into catalog words + cards** — this is the shared-memory loop in action. If you change the expected JSON shape, update both the prompt and `_parse`/`_save_turn` together.

## Deployment

Push to `main` triggers [.github/workflows/deploy.yml](.github/workflows/deploy.yml): SSH to a Hetzner VPS, `git pull`, refresh the Nginx config from [nginx/family-english.conf](nginx/family-english.conf), `docker compose up -d --build`, poll `/healthz`, then run the smoke test inside the container. App listens on `8090`; SQLite lives in the `family_db` Docker volume at `/app/data`.
