"""Проверки доступа и защиты изменяющих запросов."""

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    database_path = str(tmp_path / "access.sqlite3")
    monkeypatch.setattr(settings, "deadlines_db_path", database_path)
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.parametrize("path", ["/", "/today", "/assets/app.js", "/docs", "/openapi.json"])
def test_protected_routes_require_credentials(client, path):
    response = client.get(path)
    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Basic ")


@pytest.mark.parametrize("credentials", [None, ("bad-user", "test-password"), ("test-user", "wrong")])
def test_bad_credentials_cannot_read_deadlines(client, credentials):
    response = client.get("/today", auth=credentials)
    assert response.status_code == 401


@pytest.mark.parametrize("header", ["Basic invalid!", "Bearer secret", "Basic dXNlcm5hbWU="])
def test_malformed_authorization_returns_401(client, header):
    response = client.get("/today", headers={"Authorization": header})
    assert response.status_code == 401


@pytest.mark.parametrize("username,password", [("", "test-password"), ("test-user", ""), ("  ", "ok"), ("a:b", "ok")])
def test_missing_or_invalid_configuration_fails_closed(client, monkeypatch, username, password):
    monkeypatch.setattr(settings, "auth_username", username)
    monkeypatch.setattr(settings, "auth_password", password)
    response = client.get("/today", auth=("test-user", "test-password"))
    assert response.status_code == 503
    assert client.get("/health").json() == {"status": "ok"}


def test_authorized_browser_scenario(client):
    client.auth = ("test-user", "test-password")
    assert client.get("/").status_code == 200
    assert client.get("/assets/app.js").status_code == 200
    assert client.get("/today").json() == []

    headers = {"X-Requested-With": "DeadlineDuty"}
    payload = {"title": "Отчёт", "due_date": "2000-01-01"}
    created = client.post("/deadlines", json=payload, headers=headers)
    assert created.status_code == 200
    assert client.get("/today").json() == [created.json()]
    deadline_id = created.json()["id"]

    completed = client.post(f"/deadlines/{deadline_id}/done", headers=headers)
    assert completed.status_code == 200
    assert client.get("/today").json() == []


def test_post_requires_custom_header_even_with_valid_credentials(client):
    credentials = ("test-user", "test-password")
    payload = {"title": "Отчёт", "due_date": "2000-01-01"}
    response = client.post("/deadlines", json=payload, auth=credentials)
    assert response.status_code == 403
    assert client.get("/today", auth=credentials).json() == []


def test_cross_origin_preflight_does_not_permit_custom_header(client):
    headers = {
        "Origin": "https://example.invalid",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "x-requested-with",
    }
    response = client.options("/deadlines", headers=headers, auth=("test-user", "test-password"))
    assert "access-control-allow-origin" not in response.headers
