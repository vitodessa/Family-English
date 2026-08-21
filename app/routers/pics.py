"""Отдача пиктограмм к словам: /pic/<слово> → PNG из локального кэша.

Первый запрос по слову может подтянуть картинку с ARASAAC и сохранить в кэш;
дальше всё с диска. Ключ не нужен. Нет пиктограммы — 404 (карточка покажет эмодзи).
"""
from fastapi import APIRouter, Response
from fastapi.responses import FileResponse

from app import pictograms

router = APIRouter()


@router.get("/pic/{word}")
def pic(word: str):
    pid = pictograms.pictogram_id(word)
    if not pid:
        return Response(status_code=404)
    path = pictograms.ensure_cached(pid)
    if not path:
        return Response(status_code=404)
    return FileResponse(
        str(path),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=604800"},  # неделя в браузере
    )
