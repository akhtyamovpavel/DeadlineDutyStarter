"""Проверки страницы и её клиентского сценария."""

from pathlib import Path
import shutil
import subprocess

from fastapi.testclient import TestClient
import pytest

from app.config import settings
from app.main import app
from conftest import authorize_test_client


PROJECT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(tmp_path, monkeypatch):
    database_path = tmp_path / "web-test.sqlite3"
    monkeypatch.setattr(settings, "deadlines_db_path", str(database_path))
    with TestClient(app) as test_client:
        authorize_test_client(test_client)
        yield test_client


def test_page_and_assets_are_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'lang="ru"' in response.text
    assert 'for="title"' in response.text
    assert 'for="due-date"' in response.text
    assert 'role="status"' in response.text
    assert 'role="alert"' in response.text

    javascript = client.get("/assets/app.js")
    assert javascript.status_code == 200
    assert javascript.headers["content-type"].startswith("text/javascript")

    stylesheet = client.get("/assets/style.css")
    assert stylesheet.status_code == 200
    assert stylesheet.headers["content-type"].startswith("text/css")


def test_client_interactions():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is needed for the optional browser interaction checks")

    result = subprocess.run(
        [node, "--test", "tests/web_client.test.js"],
        cwd=PROJECT,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
