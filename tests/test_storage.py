"""Проверки сохранения данных между запусками сервиса."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

import app.main as deadline_service

PROJECT = Path(__file__).resolve().parents[1]


class FixedDate(date):
    @classmethod
    def today(cls):
        return date(2026, 1, 15)


PROCESS_CODE = '''
from datetime import date
import json
import sys

from fastapi.testclient import TestClient
import app.main as service

class FixedDate(date):
    @classmethod
    def today(cls):
        return date(2026, 1, 15)

service.date = FixedDate
with TestClient(service.app) as client:
    if sys.argv[1] == "create":
        first = client.post("/deadlines", json={"title": "first", "due_date": "2026-01-15"})
        second = client.post("/deadlines", json={"title": "second", "due_date": "2026-01-15"})
        result = [first.json(), second.json()]
    elif sys.argv[1] == "complete":
        before = client.get("/today").json()
        completed = client.post(f"/deadlines/{sys.argv[2]}/done").json()
        new = client.post("/deadlines", json={"title": "new", "due_date": "2026-01-15"}).json()
        result = {"before": before, "completed": completed, "new": new}
    else:
        today = client.get("/today").json()
        completed = client.post(f"/deadlines/{sys.argv[2]}/done").json()
        result = {"today": today, "completed": completed}
print(json.dumps(result))
'''


def run_process(database_path, operation, *arguments):
    environment = os.environ.copy()
    environment["DEADLINES_DB_PATH"] = str(database_path)
    command = [sys.executable, "-c", PROCESS_CODE, operation, *arguments]
    result = subprocess.run(
        command,
        cwd=PROJECT,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )
    return json.loads(result.stdout)


def test_deadlines_and_completion_survive_process_restarts(tmp_path):
    database_path = tmp_path / "deadlines.sqlite3"
    created = run_process(database_path, "create")
    first_id = created[0]["id"]
    second_id = created[1]["id"]

    after_restart = run_process(database_path, "complete", str(second_id))
    assert after_restart["before"] == created
    assert after_restart["completed"]["id"] == second_id
    assert after_restart["completed"]["done"] is True
    new_id = after_restart["new"]["id"]
    assert new_id not in {first_id, second_id}

    after_second_restart = run_process(database_path, "inspect", str(second_id))
    assert [item["id"] for item in after_second_restart["today"]] == [first_id, new_id]
    assert after_second_restart["completed"]["done"] is True


def test_concurrent_creates_keep_distinct_ids_and_all_data(tmp_path, monkeypatch):
    database_path = str(tmp_path / "concurrent.sqlite3")
    monkeypatch.setattr(deadline_service.settings, "deadlines_db_path", database_path)
    monkeypatch.setattr(deadline_service, "date", FixedDate)

    def create_deadline(index):
        payload = {"title": f"deadline {index}", "due_date": "2000-01-01"}
        response = client.post("/deadlines", json=payload)
        assert response.status_code == 200
        return response.json()

    with TestClient(deadline_service.app) as client:
        with ThreadPoolExecutor(max_workers=12) as workers:
            created = list(workers.map(create_deadline, range(24)))
        response = client.get("/today")

    assert response.status_code == 200
    ids = {item["id"] for item in created}
    titles = {item["title"] for item in created}
    saved = {item["id"]: item for item in response.json()}
    assert len(ids) == 24
    assert len(titles) == 24
    assert set(saved) == ids
    assert all(saved[item["id"]] == item for item in created)


def test_failed_read_rolls_back_completion(tmp_path, monkeypatch):
    database_path = str(tmp_path / "rollback.sqlite3")
    monkeypatch.setattr(deadline_service.settings, "deadlines_db_path", database_path)
    monkeypatch.setattr(deadline_service, "date", FixedDate)
    original_connect = sqlite3.connect

    class FailingReadConnection(sqlite3.Connection):
        def execute(self, statement, parameters=()):
            if statement.startswith("SELECT id, title, due_date, done"):
                raise sqlite3.OperationalError("simulated read failure")
            return super().execute(statement, parameters)

    def failing_connect(path):
        return original_connect(path, factory=FailingReadConnection)

    with TestClient(deadline_service.app) as client:
        payload = {"title": "pending", "due_date": "2000-01-01"}
        created = client.post("/deadlines", json=payload)
        deadline_id = created.json()["id"]

        with monkeypatch.context() as patch:
            patch.setattr(sqlite3, "connect", failing_connect)
            with pytest.raises(sqlite3.OperationalError, match="simulated read failure"):
                client.post(f"/deadlines/{deadline_id}/done")

        response = client.get("/today")
        assert response.status_code == 200
        assert response.json() == [created.json()]


def test_concurrent_completion_is_idempotent(tmp_path, monkeypatch):
    database_path = str(tmp_path / "completion.sqlite3")
    monkeypatch.setattr(deadline_service.settings, "deadlines_db_path", database_path)
    monkeypatch.setattr(deadline_service, "date", FixedDate)

    def complete_deadline(_):
        return client.post(f"/deadlines/{deadline_id}/done")

    with TestClient(deadline_service.app) as client:
        payload = {"title": "pending", "due_date": "2000-01-01"}
        created = client.post("/deadlines", json=payload)
        deadline_id = created.json()["id"]

        with ThreadPoolExecutor(max_workers=8) as workers:
            responses = list(workers.map(complete_deadline, range(8)))
        assert all(response.status_code == 200 for response in responses)
        assert all(response.json()["id"] == deadline_id for response in responses)
        assert all(response.json()["done"] is True for response in responses)
        assert client.get("/today").json() == []
