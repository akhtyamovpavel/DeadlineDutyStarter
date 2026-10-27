"""Однократная проверка сроков и отправка напоминаний через Telegram."""

from contextlib import closing
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from datetime import time
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from urllib.request import Request
from urllib.request import urlopen
from zoneinfo import ZoneInfo
from zoneinfo import ZoneInfoNotFoundError


@dataclass(frozen=True)
class ReminderConfig:
    database_path: str
    token: str = field(repr=False)
    chat_id: str = field(repr=False)
    timezone: ZoneInfo
    send_time: time
    days_before: int


def read_config(environment):
    names = [
        "DEADLINES_DB_PATH",
        "REMINDER_TELEGRAM_TOKEN",
        "REMINDER_CHAT_ID",
        "REMINDER_TIMEZONE",
        "REMINDER_TIME",
        "REMINDER_DAYS_BEFORE",
    ]
    for name in names:
        if not environment.get(name, "").strip():
            raise ValueError(f"Required setting is missing: {name}")

    token = environment["REMINDER_TELEGRAM_TOKEN"]
    if re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]+", token) is None:
        raise ValueError("REMINDER_TELEGRAM_TOKEN has an invalid format")
    chat_id = environment["REMINDER_CHAT_ID"]
    if "\n" in chat_id or "\r" in chat_id:
        raise ValueError("REMINDER_CHAT_ID has an invalid format")

    try:
        timezone = ZoneInfo(environment["REMINDER_TIMEZONE"])
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("REMINDER_TIMEZONE must name an installed IANA time zone") from None

    value = environment["REMINDER_TIME"]
    if re.fullmatch(r"[0-9]{2}:[0-9]{2}", value) is None:
        raise ValueError("REMINDER_TIME must use HH:MM")
    try:
        send_time = time.fromisoformat(value)
    except ValueError:
        raise ValueError("REMINDER_TIME must use a valid 24-hour time") from None

    try:
        days_before = int(environment["REMINDER_DAYS_BEFORE"])
    except ValueError:
        raise ValueError("REMINDER_DAYS_BEFORE must be an integer") from None
    if days_before < 1 or days_before > 365:
        raise ValueError("REMINDER_DAYS_BEFORE must be between 1 and 365")

    return ReminderConfig(
        database_path=environment["DEADLINES_DB_PATH"],
        token=token,
        chat_id=chat_id,
        timezone=timezone,
        send_time=send_time,
        days_before=days_before,
    )


def send_telegram(token, chat_id, message):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {"chat_id": chat_id, "text": message}
    payload = json.dumps(data).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    request = Request(url, data=payload, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=10) as response:
            result = json.load(response)
        return result.get("ok") is True
    except Exception:
        # Исключение может содержать URL с токеном, поэтому его не записываем.
        return False


def run_reminders(config, now, send):
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Current time must include a time zone")
    local_now = now.astimezone(config.timezone)
    target_date = local_now.date() + timedelta(days=config.days_before)
    database_uri = Path(config.database_path).resolve().as_uri() + "?mode=rw"
    recipient = hashlib.sha256(config.chat_id.encode("utf-8")).hexdigest()
    failures = 0

    with closing(sqlite3.connect(database_uri, uri=True, timeout=10)) as connection:
        connection.execute("SELECT id, title, due_date, done FROM deadlines LIMIT 0")
        with connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS reminder_attempts (
                    deadline_id INTEGER NOT NULL,
                    recipient TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (state IN ('attempted', 'sent', 'failed')),
                    PRIMARY KEY (deadline_id, recipient)
                )
                """
            )
        if local_now.time().replace(tzinfo=None) < config.send_time:
            return 0
        candidates = connection.execute(
            "SELECT id, title FROM deadlines WHERE done = 0 AND due_date = ? ORDER BY id",
            (target_date.isoformat(),),
        ).fetchall()

        for deadline_id, title in candidates:
            with connection:
                claimed = connection.execute(
                    """
                    INSERT OR IGNORE INTO reminder_attempts (deadline_id, recipient, state)
                    SELECT id, ?, 'attempted' FROM deadlines
                    WHERE id = ? AND done = 0 AND due_date = ?
                    """,
                    (recipient, deadline_id, target_date.isoformat()),
                ).rowcount
            if claimed == 0:
                continue

            safe_title = title[:1800]
            message = f"Дедлайн: {safe_title}\nСрок: {target_date.isoformat()}"
            try:
                sent = send(config.token, config.chat_id, message)
            except Exception:
                # Транспорт может передать в исключении токен, поэтому не выводим его.
                sent = False
            state = "failed"
            if sent:
                state = "sent"
            else:
                failures += 1
            with connection:
                connection.execute(
                    "UPDATE reminder_attempts SET state = ? WHERE deadline_id = ? AND recipient = ?",
                    (state, deadline_id, recipient),
                )

    return failures


def main():
    try:
        config = read_config(os.environ)
        now = datetime.now(config.timezone)
        failures = run_reminders(config, now, send_telegram)
    except (ValueError, OSError, sqlite3.Error):
        print("Reminder configuration or database is unavailable.", file=sys.stderr)
        return 1
    if failures:
        print("Some reminders failed; no automatic retry will be made.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
