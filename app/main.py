"""Дежурный по дедлайнам: сквозной проект курса."""

from contextlib import asynccontextmanager
from contextlib import closing
from datetime import date
import sqlite3

from fastapi import FastAPI
from fastapi import HTTPException
from pydantic import BaseModel

from app.config import settings
from app.web import router as web_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    query = """
        CREATE TABLE IF NOT EXISTS deadlines (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            due_date TEXT NOT NULL,
            done INTEGER NOT NULL
        )
    """
    with closing(sqlite3.connect(settings.deadlines_db_path)) as connection:
        with connection:
            connection.execute(query)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(web_router)


class DeadlineIn(BaseModel):
    title: str
    due_date: date


class Deadline(BaseModel):
    id: int
    title: str
    due_date: date
    done: bool = False


@app.get("/health")
def health() -> dict[str, str]:
    """Проверка живости. Первое, что спрашивают у сервиса при выкатке."""
    return {"status": "ok"}


@app.post("/deadlines", response_model=Deadline)
def create_deadline(payload: DeadlineIn) -> Deadline:
    with closing(sqlite3.connect(settings.deadlines_db_path)) as connection:
        with connection:
            cursor = connection.execute(
                "INSERT INTO deadlines (title, due_date, done) VALUES (?, ?, 0)",
                (payload.title, payload.due_date.isoformat()),
            )
            deadline_id = cursor.lastrowid
    return Deadline(id=deadline_id, title=payload.title, due_date=payload.due_date)


@app.get("/today", response_model=list[Deadline])
def today() -> list[Deadline]:
    """Главный сценарий продукта: что горит прямо сегодня."""
    current = date.today()
    query = """
        SELECT id, title, due_date, done FROM deadlines
        WHERE done = 0 AND due_date <= ? ORDER BY id
    """
    with closing(sqlite3.connect(settings.deadlines_db_path)) as connection:
        rows = connection.execute(
            query,
            (current.isoformat(),),
        ).fetchall()
    result = []
    for row in rows:
        deadline = Deadline(id=row[0], title=row[1], due_date=row[2], done=bool(row[3]))
        result.append(deadline)
    return result


@app.post("/deadlines/{deadline_id}/done", response_model=Deadline)
def mark_done(deadline_id: int) -> Deadline:
    with closing(sqlite3.connect(settings.deadlines_db_path)) as connection:
        with connection:
            cursor = connection.execute(
                "UPDATE deadlines SET done = 1 WHERE id = ?",
                (deadline_id,),
            )
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Дедлайн не найден")
            row = connection.execute(
                "SELECT id, title, due_date, done FROM deadlines WHERE id = ?",
                (deadline_id,),
            ).fetchone()
    return Deadline(id=row[0], title=row[1], due_date=row[2], done=bool(row[3]))
