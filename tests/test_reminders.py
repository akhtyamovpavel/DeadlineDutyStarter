from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from datetime import time
from datetime import timezone
import io
import json
import os
import sqlite3
import subprocess
import sys
import threading
from zoneinfo import ZoneInfo

import pytest

from app.reminders import ReminderConfig
from app.reminders import read_config
from app.reminders import run_reminders
from app.reminders import send_telegram


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "reminders.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE deadlines (id INTEGER PRIMARY KEY, title TEXT, due_date TEXT, done INTEGER)"
        )
        connection.executemany(
            "INSERT INTO deadlines VALUES (?, ?, ?, ?)",
            [
                (1, "Завтра", "2026-01-16", 0),
                (2, "Завершено", "2026-01-16", 1),
                (3, "Прошло", "2026-01-14", 0),
                (4, "Позднее", "2026-01-17", 0),
            ],
        )
    return path


@pytest.fixture
def config(database):
    return ReminderConfig(
        database_path=str(database),
        token="12345:fake_token",
        chat_id="123456",
        timezone=ZoneInfo("Europe/Moscow"),
        send_time=time(9, 0),
        days_before=1,
    )


def test_sends_only_due_unfinished_after_local_time_once(config):
    messages = []

    def send(token, chat_id, message):
        messages.append((token, chat_id, message))
        return True

    before = datetime(2026, 1, 15, 5, 59, tzinfo=timezone.utc)
    after = datetime(2026, 1, 15, 6, 0, tzinfo=timezone.utc)
    assert run_reminders(config, before, send) == 0
    assert messages == []
    assert run_reminders(config, after, send) == 0
    assert run_reminders(config, after, send) == 0
    assert len(messages) == 1
    assert messages[0][2] == "Дедлайн: Завтра\nСрок: 2026-01-16"


def test_failure_is_recorded_without_automatic_retry(config):
    calls = []

    def failing_send(token, chat_id, message):
        calls.append(message)
        raise RuntimeError("12345:fake_token")

    now = datetime(2026, 1, 15, 6, 0, tzinfo=timezone.utc)
    assert run_reminders(config, now, failing_send) == 1
    assert run_reminders(config, now, failing_send) == 0
    assert len(calls) == 1
    with sqlite3.connect(config.database_path) as connection:
        rows = connection.execute("SELECT state, recipient FROM reminder_attempts").fetchall()
    assert rows[0][0] == "failed"
    assert config.chat_id not in rows[0][1]


def test_parallel_runs_claim_only_one_attempt(config):
    entered = threading.Event()
    release = threading.Event()
    calls = []

    def slow_send(token, chat_id, message):
        calls.append(message)
        entered.set()
        assert release.wait(timeout=5)
        return True

    now = datetime(2026, 1, 15, 6, 0, tzinfo=timezone.utc)
    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(run_reminders, config, now, slow_send)
        assert entered.wait(timeout=5)
        second = workers.submit(run_reminders, config, now, slow_send)
        assert second.result(timeout=5) == 0
        release.set()
        assert first.result(timeout=5) == 0
    assert len(calls) == 1


def test_previous_attempt_after_crash_is_not_retried(config):
    import hashlib

    recipient = hashlib.sha256(config.chat_id.encode("utf-8")).hexdigest()
    with sqlite3.connect(config.database_path) as connection:
        connection.execute(
            "CREATE TABLE reminder_attempts (deadline_id INTEGER, recipient TEXT, state TEXT, PRIMARY KEY (deadline_id, recipient))"
        )
        connection.execute("INSERT INTO reminder_attempts VALUES (1, ?, 'attempted')", (recipient,))
    now = datetime(2026, 1, 15, 6, 0, tzinfo=timezone.utc)
    calls = []
    assert run_reminders(config, now, lambda *args: calls.append(args)) == 0
    assert calls == []


def test_missed_day_does_not_send_late(config):
    now = datetime(2026, 1, 16, 6, 0, tzinfo=timezone.utc)
    calls = []

    def send(*args):
        calls.append(args)
        return True

    assert run_reminders(config, now, send) == 0
    assert len(calls) == 1
    assert "Позднее" in calls[0][2]
    assert "Завтра" not in calls[0][2]


def test_config_requires_explicit_values():
    values = {
        "DEADLINES_DB_PATH": "data.sqlite3",
        "REMINDER_TELEGRAM_TOKEN": "12345:fake_token",
        "REMINDER_CHAT_ID": "123456",
        "REMINDER_TIMEZONE": "Europe/Moscow",
        "REMINDER_TIME": "09:00",
        "REMINDER_DAYS_BEFORE": "1",
    }
    assert read_config(values).days_before == 1
    for key in values:
        missing = dict(values)
        del missing[key]
        with pytest.raises(ValueError):
            read_config(missing)
    for key, value in [("REMINDER_TIME", "25:00"), ("REMINDER_DAYS_BEFORE", "0")]:
        invalid = dict(values)
        invalid[key] = value
        with pytest.raises(ValueError):
            read_config(invalid)


def test_invalid_database_is_reported_before_scheduled_time(tmp_path, config):
    from dataclasses import replace

    missing = tmp_path / "missing.sqlite3"
    invalid = replace(config, database_path=str(missing))
    before = datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(sqlite3.OperationalError):
        run_reminders(invalid, before, lambda *args: True)
    assert not missing.exists()


def test_nonexistent_local_time_sends_after_clock_change(database, config):
    from dataclasses import replace

    with sqlite3.connect(database) as connection:
        connection.execute("INSERT INTO deadlines VALUES (5, 'DST', '2026-03-09', 0)")
    daylight = replace(config, timezone=ZoneInfo("America/New_York"), send_time=time(2, 30))
    before = datetime(2026, 3, 8, 6, 59, tzinfo=timezone.utc)
    after = datetime(2026, 3, 8, 7, 0, tzinfo=timezone.utc)
    calls = []

    def send(*args):
        calls.append(args)
        return True

    assert run_reminders(daylight, before, send) == 0
    assert calls == []
    assert run_reminders(daylight, after, send) == 0
    assert len(calls) == 1
    assert "DST" in calls[0][2]


def test_telegram_request_uses_json_and_redacts_failures(monkeypatch):
    captured = []

    def fake_urlopen(request, timeout):
        captured.append((request, timeout))
        return io.BytesIO(b'{"ok": true}')

    monkeypatch.setattr("app.reminders.urlopen", fake_urlopen)
    assert send_telegram("12345:fake_token", "123456", "Текст") is True
    request, timeout = captured[0]
    assert request.full_url == "https://api.telegram.org/bot12345:fake_token/sendMessage"
    assert json.loads(request.data) == {"chat_id": "123456", "text": "Текст"}
    assert timeout == 10

    def broken_urlopen(request, timeout):
        raise OSError(request.full_url)

    monkeypatch.setattr("app.reminders.urlopen", broken_urlopen)
    assert send_telegram("12345:fake_token", "123456", "Текст") is False


def test_cli_does_not_create_missing_database_or_print_secret(tmp_path):
    environment = os.environ.copy()
    secret = "12345:fake_token"
    environment.update({
        "DEADLINES_DB_PATH": str(tmp_path / "missing.sqlite3"),
        "REMINDER_TELEGRAM_TOKEN": secret,
        "REMINDER_CHAT_ID": "123456",
        "REMINDER_TIMEZONE": "UTC",
        "REMINDER_TIME": "00:00",
        "REMINDER_DAYS_BEFORE": "1",
    })
    result = subprocess.run(
        [sys.executable, "-m", "app.reminders"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 1
    assert secret not in result.stdout + result.stderr
    assert not (tmp_path / "missing.sqlite3").exists()
