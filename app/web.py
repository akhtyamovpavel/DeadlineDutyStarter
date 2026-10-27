"""Страница для работы с дедлайнами."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse


router = APIRouter(include_in_schema=False)
STATIC_DIR = Path(__file__).resolve().parent / "static"


@router.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@router.get("/assets/app.js")
def javascript() -> FileResponse:
    return FileResponse(STATIC_DIR / "app.js", media_type="text/javascript")


@router.get("/assets/style.css")
def stylesheet() -> FileResponse:
    return FileResponse(STATIC_DIR / "style.css", media_type="text/css")
