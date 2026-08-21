"""Плановые задания для отчётов бота.

Запуск в контейнере (см. cron на сервере):
  python -m app.jobs morning   # утреннее напоминание (кто ещё не занимался + серии)
  python -m app.jobs evening   # вечерний статус семьи (в т.ч. «не занимался»)
  python -m app.jobs weekly    # недельный дайджест

Если Telegram не настроен (нет токена/chat_id) — задание тихо ничего не шлёт.
"""
import sys

from app.database import SessionLocal
from app.report_service import run_evening, run_morning, run_weekly

JOBS = {"morning": run_morning, "evening": run_evening, "weekly": run_weekly}


def main():
    job = sys.argv[1] if len(sys.argv) > 1 else ""
    fn = JOBS.get(job)
    if not fn:
        print("usage: python -m app.jobs {evening|weekly}")
        return
    db = SessionLocal()
    try:
        ok = fn(db)
        print("%s -> %s" % (job, "отправлено" if ok else "не отправлено (нет токена/ошибка)"))
    finally:
        db.close()


if __name__ == "__main__":
    main()
