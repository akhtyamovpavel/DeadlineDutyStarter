"""Проверки основного сценария сервиса дедлайнов."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

import app.main as deadline_service
from conftest import authorize_test_client


class FixedDate(date):
    @classmethod
    def today(cls):
        return date(2026, 1, 15)


@pytest.fixture(autouse=True)
def isolated_storage_and_date(monkeypatch, tmp_path):
    database_path = str(tmp_path / "deadlines.sqlite3")
    monkeypatch.setattr(deadline_service.settings, "deadlines_db_path", database_path)
    monkeypatch.setattr(deadline_service, "date", FixedDate)


@pytest.fixture
def client():
    with TestClient(deadline_service.app) as test_client:
        authorize_test_client(test_client)
        yield test_client


def test_health_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_deadline(client):
    payload = {"title": "сдать лабу", "due_date": "2026-01-15"}
    response = client.post("/deadlines", json=payload)
    assert response.status_code == 200
    assert response.json()["title"] == "сдать лабу"
    assert response.json()["done"] is False


def test_today_includes_overdue_and_today_but_not_future_or_done(client):
    deadlines = [
        {"title": "просрочено", "due_date": "2026-01-14"},
        {"title": "сегодня", "due_date": "2026-01-15"},
        {"title": "позже", "due_date": "2026-01-16"},
        {"title": "выполнено", "due_date": "2026-01-15"},
    ]
    for payload in deadlines:
        response = client.post("/deadlines", json=payload)
        assert response.status_code == 200
        if payload["title"] == "выполнено":
            completed_id = response.json()["id"]
            completion = client.post(f"/deadlines/{completed_id}/done")
            assert completion.status_code == 200

    response = client.get("/today")
    assert response.status_code == 200
    titles = {item["title"] for item in response.json()}
    assert titles == {"просрочено", "сегодня"}


def test_completed_deadline_disappears_from_today(client):
    payload = {"title": "сдать отчёт", "due_date": "2026-01-15"}
    created = client.post("/deadlines", json=payload)
    deadline_id = created.json()["id"]

    response = client.post(f"/deadlines/{deadline_id}/done")
    assert response.status_code == 200
    assert client.get("/today").json() == []


def test_nonexistent_deadline_returns_404(client):
    response = client.post("/deadlines/9999/done")
    assert response.status_code == 404
