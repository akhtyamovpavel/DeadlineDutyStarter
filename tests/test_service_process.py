"""Проверка основного сценария через работающий HTTP-сервис."""

from contextlib import contextmanager
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx


PROJECT = Path(__file__).resolve().parents[1]


@contextmanager
def running_service(database_path):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(32)
    port = listener.getsockname()[1]
    environment = os.environ.copy()
    environment["DEADLINES_DB_PATH"] = str(database_path)
    command = [sys.executable, "-m", "uvicorn", "app.main:app"]
    command.extend(["--fd", str(listener.fileno()), "--no-access-log"])
    process = subprocess.Popen(
        command,
        cwd=PROJECT,
        env=environment,
        pass_fds=(listener.fileno(),),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    listener.close()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False) as client:
            deadline = time.monotonic() + 10
            while True:
                if process.poll() is not None:
                    raise AssertionError("Uvicorn exited before becoming ready")
                try:
                    response = client.get("/health", timeout=1)
                    if response.status_code == 200:
                        break
                except httpx.RequestError:
                    pass
                if time.monotonic() >= deadline:
                    raise AssertionError("Uvicorn did not become ready")
                time.sleep(0.05)
            yield client
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def test_http_scenario_and_persistence_across_service_restarts(tmp_path):
    database_path = tmp_path / "deadline-duty.sqlite3"
    payload = {"title": "check service", "due_date": "2000-01-01"}
    with running_service(database_path) as client:
        health = client.get("/health")
        assert health.json() == {"status": "ok"}
        assert client.get("/").status_code == 200
        response = client.post("/deadlines", json=payload)
        assert response.status_code == 200
        created = response.json()
        assert client.get("/today").json() == [created]

    with running_service(database_path) as client:
        assert client.get("/today").json() == [created]
        response = client.post(f"/deadlines/{created['id']}/done")
        assert response.status_code == 200
        assert response.json()["done"] is True

    with running_service(database_path) as client:
        assert client.get("/today").json() == []
