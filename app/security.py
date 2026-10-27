"""Проверка доступа одного пользователя к сервису."""

import base64
import binascii
import secrets

from fastapi import Request
from fastapi.responses import JSONResponse

from app.config import settings


def authorize(request: Request) -> JSONResponse | None:
    if request.method == "GET" and request.url.path == "/health":
        return None

    username = settings.auth_username
    password = settings.auth_password
    if not username.strip() or not password.strip() or ":" in username:
        return JSONResponse({"detail": "Доступ не настроен"}, status_code=503)

    authorization = request.headers.get("authorization", "")
    scheme, separator, encoded = authorization.partition(" ")
    if scheme.lower() != "basic" or not separator:
        return unauthorized()

    try:
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return unauthorized()
    supplied_username, separator, supplied_password = decoded.partition(":")
    if not separator:
        return unauthorized()

    expected_username = username.encode("utf-8")
    expected_password = password.encode("utf-8")
    correct_username = secrets.compare_digest(supplied_username.encode("utf-8"), expected_username)
    correct_password = secrets.compare_digest(supplied_password.encode("utf-8"), expected_password)
    if not correct_username or not correct_password:
        return unauthorized()

    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if request.headers.get("x-requested-with") != "DeadlineDuty":
            return JSONResponse({"detail": "Недопустимый запрос"}, status_code=403)
    return None


def unauthorized() -> JSONResponse:
    headers = {"WWW-Authenticate": 'Basic realm="DeadlineDuty", charset="UTF-8"'}
    return JSONResponse({"detail": "Требуется авторизация"}, status_code=401, headers=headers)
