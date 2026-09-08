"""Дежурный по дедлайнам: сквозной проект курса.

Первая неделя жизни проекта: сроки хранятся в памяти, есть три действия и
проверка живости. Всё остальное появится на следующих занятиях, и появится
не потому, что так принято, а потому что этого потребует спецификация.
"""

from datetime import date

from fastapi import FastAPI
from fastapi import HTTPException
from pydantic import BaseModel

from app.config import settings

app = FastAPI(title=settings.app_name)

# Временное хранилище. На неделе 5 его заменит база данных.
deadlines: dict[int, "Deadline"] = {}
next_id = 1


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
    global next_id
    deadline = Deadline(id=next_id, title=payload.title, due_date=payload.due_date)
    deadlines[next_id] = deadline
    next_id += 1
    return deadline


@app.get("/today", response_model=list[Deadline])
def today() -> list[Deadline]:
    """Главный сценарий продукта: что горит прямо сегодня."""
    current = date.today()
    result = []
    for deadline in deadlines.values():
        if deadline.done:
            continue
        if deadline.due_date <= current:
            result.append(deadline)
    return result


@app.post("/deadlines/{deadline_id}/done", response_model=Deadline)
def mark_done(deadline_id: int) -> Deadline:
    if deadline_id not in deadlines:
        raise HTTPException(status_code=404, detail="Дедлайн не найден")
    deadline = deadlines[deadline_id]
    deadline.done = True
    return deadline
