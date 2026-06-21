"""Точка входа: запуск:  uvicorn app.main:app --reload"""

from contextlib import asynccontextmanager

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.config import APP_TITLE, BASE_DIR, SECRET_KEY
from app.database import Base, SessionLocal, engine, get_db
from app.deps import get_current_user
from app.routers import admin, auth, study, vocab
from app.seed import ensure_admin, ensure_grammar_topics, seed_words
from app.templating import render

# Создаём схему (Alembic появится позже). На чистой БД — поднимет все таблицы.
Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app):
    db = SessionLocal()
    try:
        ensure_grammar_topics(db)
        seed_words(db)
        ensure_admin(db)
    finally:
        db.close()
    yield


from fastapi import FastAPI  # noqa: E402  (после lifespan для читаемости)

app = FastAPI(title=APP_TITLE, lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")

app.include_router(auth.router)
app.include_router(study.router)
app.include_router(vocab.router)
app.include_router(admin.router)


@app.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    if get_current_user(request, db):
        return RedirectResponse("/dashboard", status_code=302)
    return render(request, "home.html", db=db)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
