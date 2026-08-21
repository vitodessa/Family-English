"""Разовый прогрев кэша пиктограмм: скачать все картинки из карты в data/pics.

Запуск внутри контейнера:
  docker compose exec -T family_english python scripts/fetch_pictograms.py

После прогрева приложение отдаёт картинки полностью офлайн (наружу не ходит).
Идемпотентно: уже скачанные пропускает.
"""
import sys
from concurrent.futures import ThreadPoolExecutor

from app import pictograms


def one(item):
    word, pid = item
    p = pictograms.ensure_cached(pid)
    return bool(p)


def main():
    items = list(pictograms._MAP.items())
    print("картинок к прогреву:", len(items), flush=True)
    ok = 0
    done = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        for res in ex.map(one, items):
            done += 1
            ok += 1 if res else 0
            if done % 500 == 0:
                print("скачано %d/%d (успешно %d)" % (done, len(items), ok), flush=True)
    print("ГОТОВО: в кэше %d/%d" % (ok, len(items)), flush=True)
    if ok < len(items):
        sys.stderr.write("часть картинок не скачалась — повторный запуск дотянет\n")


if __name__ == "__main__":
    main()
