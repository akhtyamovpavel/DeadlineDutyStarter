"""Базовые проверки. Их запуск одной командой это и есть test command проекта."""

from datetime import date
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.main import deadlines

client = TestClient(app)


@pytest.fixture(autouse=True)
def чистое_хранилище():
    """Каждый тест начинается с пустого списка, иначе они влияют друг на друга."""
    deadlines.clear()
    yield
    deadlines.clear()


def test_health_отвечает_ok():
    ответ = client.get("/health")
    assert ответ.status_code == 200
    assert ответ.json() == {"status": "ok"}


def test_дедлайн_создаётся():
    данные = {"title": "сдать лабу", "due_date": str(date.today())}
    ответ = client.post("/deadlines", json=данные)
    assert ответ.status_code == 200
    assert ответ.json()["title"] == "сдать лабу"
    assert ответ.json()["done"] is False


def test_сегодня_показывает_то_что_горит():
    сегодня = str(date.today())
    послезавтра = str(date.today() + timedelta(days=2))
    client.post("/deadlines", json={"title": "горит", "due_date": сегодня})
    client.post("/deadlines", json={"title": "потом", "due_date": послезавтра})

    ответ = client.get("/today")
    названия = [item["title"] for item in ответ.json()]
    assert названия == ["горит"]


def test_отмеченный_дедлайн_уходит_из_списка():
    данные = {"title": "сдать отчёт", "due_date": str(date.today())}
    создан = client.post("/deadlines", json=данные)
    deadline_id = создан.json()["id"]

    client.post(f"/deadlines/{deadline_id}/done")

    assert client.get("/today").json() == []


def test_несуществующий_дедлайн_отдаёт_404():
    ответ = client.post("/deadlines/9999/done")
    assert ответ.status_code == 404
