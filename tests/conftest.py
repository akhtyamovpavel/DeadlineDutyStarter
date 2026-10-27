import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def test_credentials(monkeypatch):
    monkeypatch.setattr(settings, "auth_username", "test-user")
    monkeypatch.setattr(settings, "auth_password", "test-password")


def authorize_test_client(client):
    client.auth = ("test-user", "test-password")
    client.headers["X-Requested-With"] = "DeadlineDuty"
    return client
