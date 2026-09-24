"""Durable local timer state. No household or account data is required."""

from __future__ import annotations

import sqlite3
import time
import uuid
import os
import stat
import math
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class TimerStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name == "posix":
            if stat.S_IMODE(path.parent.stat().st_mode) & 0o077:
                raise ValueError("Alltron data directory is accessible by other users; choose a private directory or set its permissions to 0700")
            if path.is_symlink():
                raise ValueError("Timer database must not be a symbolic link")
            try:
                descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                if not path.is_file():
                    raise ValueError("Timer database must be a regular file") from None
            else:
                os.close(descriptor)
            if stat.S_IMODE(path.stat().st_mode) & 0o077:
                raise ValueError("Timer database is accessible by other users; set its permissions to 0600")
        with self._connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS timers ("
                "id TEXT PRIMARY KEY, label TEXT NOT NULL, created_at REAL NOT NULL, "
                "due_at REAL NOT NULL, state TEXT NOT NULL CHECK (state IN ('running', 'cancelled', 'done')))"
            )
            columns = {row[1] for row in db.execute("PRAGMA table_info(timers)")}
            if "request_id" not in columns:
                db.execute("ALTER TABLE timers ADD COLUMN request_id TEXT")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS timers_request_id ON timers(request_id)")
            db.execute(
                "CREATE TABLE IF NOT EXISTS alarms ("
                "id TEXT PRIMARY KEY, label TEXT NOT NULL, created_at REAL NOT NULL, "
                "due_at REAL NOT NULL, state TEXT NOT NULL CHECK (state IN ('running', 'cancelled', 'done')), "
                "request_id TEXT UNIQUE)"
            )
            alarm_columns = {row[1] for row in db.execute("PRAGMA table_info(alarms)")}
            if "delivery" not in alarm_columns:
                db.execute("ALTER TABLE alarms ADD COLUMN delivery TEXT DEFAULT 'pending'")
            db.execute(
                "CREATE TABLE IF NOT EXISTS shopping_items ("
                "id TEXT PRIMARY KEY, text TEXT NOT NULL, item_key TEXT NOT NULL, "
                "created_at REAL NOT NULL, done INTEGER NOT NULL DEFAULT 0 CHECK (done IN (0, 1)))"
            )
            db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS shopping_open_key "
                "ON shopping_items(item_key) WHERE done = 0"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS shopping_requests ("
                "request_id TEXT PRIMARY KEY, action TEXT NOT NULL, item_key TEXT NOT NULL, "
                "item_id TEXT, succeeded INTEGER NOT NULL CHECK (succeeded IN (0, 1)))"
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def add(self, seconds: int, label: str = "Timer", *, now: float | None = None,
            request_id: str | None = None) -> dict:
        if not 1 <= seconds <= 86400:
            raise ValueError("Timer duration must be between 1 second and 24 hours")
        label = label.strip()
        if not label or len(label) > 80:
            raise ValueError("Timer label must contain 1 to 80 characters")
        timestamp = time.time() if now is None else now
        timer = {
            "id": str(uuid.uuid4()),
            "label": label,
            "created_at": timestamp,
            "due_at": timestamp + seconds,
            "state": "running",
            "request_id": request_id,
        }
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if request_id is not None:
                existing = db.execute(
                    "SELECT * FROM timers WHERE request_id = ?", (request_id,)
                ).fetchone()
                if existing:
                    if existing["label"] != label or round(existing["due_at"] - existing["created_at"]) != seconds:
                        raise ValueError("Request ID was already used for a different timer")
                    return dict(existing)
            if db.execute("SELECT COUNT(*) FROM timers WHERE state = 'running'").fetchone()[0] >= 100:
                raise ValueError("At most 100 running timers are supported")
            db.execute(
                "INSERT INTO timers (id, label, created_at, due_at, state, request_id) "
                "VALUES (:id, :label, :created_at, :due_at, :state, :request_id)",
                timer,
            )
        return timer

    def list(self, *, now: float | None = None) -> list[dict]:
        timestamp = time.time() if now is None else now
        with self._connect() as db:
            db.execute("UPDATE timers SET state = 'done' WHERE state = 'running' AND due_at <= ?", (timestamp,))
            rows = db.execute(
                "SELECT id, label, created_at, due_at, state FROM timers "
                "WHERE state != 'cancelled' ORDER BY due_at DESC LIMIT 100"
            ).fetchall()
        return [dict(row) for row in rows]

    def cancel(self, timer_id: str) -> bool:
        with self._connect() as db:
            result = db.execute(
                "UPDATE timers SET state = 'cancelled' WHERE id = ? AND state = 'running'", (timer_id,)
            )
            return result.rowcount == 1

    def add_alarm(self, due_at: float, label: str = "Alarm", *, now: float | None = None,
                  request_id: str | None = None) -> dict:
        timestamp = time.time() if now is None else now
        try:
            valid_deadline = math.isfinite(due_at) and 1 <= due_at - timestamp <= 365 * 86400
        except (OverflowError, TypeError):
            valid_deadline = False
        if not valid_deadline:
            raise ValueError("Alarm must be between 1 second and 365 days from now")
        label = label.strip()
        if not label or len(label) > 80:
            raise ValueError("Alarm label must contain 1 to 80 characters")
        alarm = {"id": str(uuid.uuid4()), "label": label, "created_at": timestamp,
                 "due_at": due_at, "state": "running", "request_id": request_id,
                 "delivery": "pending"}
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if request_id is not None:
                existing = db.execute("SELECT * FROM alarms WHERE request_id = ?", (request_id,)).fetchone()
                if existing:
                    if (existing["label"] != label or
                            round(existing["due_at"] - existing["created_at"]) != round(due_at - timestamp)):
                        raise ValueError("Request ID was already used for a different alarm")
                    return dict(existing)
            if db.execute("SELECT COUNT(*) FROM alarms WHERE state = 'running'").fetchone()[0] >= 100:
                raise ValueError("At most 100 running alarms are supported")
            db.execute(
                "INSERT INTO alarms (id, label, created_at, due_at, state, request_id, delivery) "
                "VALUES (:id, :label, :created_at, :due_at, :state, :request_id, :delivery)", alarm
            )
        return alarm

    def list_alarms(self, *, now: float | None = None) -> list[dict]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT id, label, created_at, due_at, state, delivery FROM alarms "
                "WHERE state != 'cancelled' ORDER BY state DESC, due_at ASC LIMIT 100"
            ).fetchall()
        return [dict(row) for row in rows]

    def due_alarms(self, *, now: float | None = None) -> list[dict]:
        timestamp = time.time() if now is None else now
        with self._connect() as db:
            rows = db.execute(
                "SELECT id, label, due_at FROM alarms WHERE state = 'running' AND due_at <= ? "
                "ORDER BY due_at ASC LIMIT 100", (timestamp,)
            ).fetchall()
        return [dict(row) for row in rows]

    def finish_alarm(self, alarm_id: str, delivery: str) -> bool:
        if delivery not in {"played", "missed"}:
            raise ValueError("Invalid alarm delivery state")
        with self._connect() as db:
            result = db.execute(
                "UPDATE alarms SET state = 'done', delivery = ? WHERE id = ? AND state = 'running'",
                (delivery, alarm_id),
            )
            return result.rowcount == 1

    def cancel_alarm(self, alarm_id: str) -> bool:
        with self._connect() as db:
            result = db.execute(
                "UPDATE alarms SET state = 'cancelled' WHERE id = ? AND state = 'running'", (alarm_id,)
            )
            return result.rowcount == 1

    def add_shopping_item(self, text: str, *, now: float | None = None,
                          request_id: str | None = None) -> dict:
        if not isinstance(text, str):
            raise ValueError("Item must be text")
        item_text = " ".join(text.split())
        if not item_text or len(item_text) > 120:
            raise ValueError("Item must contain 1 to 120 characters")
        key = item_text.casefold()
        item = {"id": str(uuid.uuid4()), "text": item_text, "item_key": key,
                "created_at": time.time() if now is None else now, "done": 0}
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if request_id is not None:
                receipt = db.execute("SELECT * FROM shopping_requests WHERE request_id = ?",
                                     (request_id,)).fetchone()
                if receipt:
                    if receipt["action"] != "add" or receipt["item_key"] != key:
                        raise ValueError("Request ID was already used for a different shopping action")
                    return dict(db.execute(
                        "SELECT id, text, created_at, done FROM shopping_items WHERE id = ?",
                        (receipt["item_id"],)
                    ).fetchone())
            active = db.execute("SELECT id FROM shopping_items WHERE item_key = ? AND done = 0",
                                (key,)).fetchone()
            if not active and db.execute("SELECT COUNT(*) FROM shopping_items WHERE done = 0").fetchone()[0] >= 200:
                raise ValueError("At most 200 open shopping items are supported")
            db.execute(
                "INSERT OR IGNORE INTO shopping_items (id, text, item_key, created_at, done) "
                "VALUES (:id, :text, :item_key, :created_at, :done)", item
            )
            row = db.execute(
                "SELECT id, text, created_at, done FROM shopping_items WHERE item_key = ? AND done = 0", (key,)
            ).fetchone()
            if request_id is not None:
                db.execute("INSERT INTO shopping_requests VALUES (?, 'add', ?, ?, 1)",
                           (request_id, key, row["id"]))
        return dict(row)

    def list_shopping_items(self) -> list[dict]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT id, text, created_at, done FROM shopping_items "
                "ORDER BY done, created_at DESC LIMIT 200"
            ).fetchall()
        return [dict(row) for row in rows]

    def complete_shopping_item(self, item_id: str) -> bool:
        with self._connect() as db:
            result = db.execute(
                "UPDATE shopping_items SET done = 1 WHERE id = ? AND done = 0", (item_id,)
            )
            return result.rowcount == 1

    def complete_shopping_text(self, text: str, *, request_id: str | None = None) -> bool:
        key = " ".join(text.split()).casefold()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if request_id is not None:
                receipt = db.execute("SELECT * FROM shopping_requests WHERE request_id = ?",
                                     (request_id,)).fetchone()
                if receipt:
                    if receipt["action"] != "complete" or receipt["item_key"] != key:
                        raise ValueError("Request ID was already used for a different shopping action")
                    return bool(receipt["succeeded"])
            result = db.execute(
                "UPDATE shopping_items SET done = 1 WHERE item_key = ? AND done = 0", (key,)
            )
            succeeded = result.rowcount == 1
            if request_id is not None:
                db.execute("INSERT INTO shopping_requests VALUES (?, 'complete', ?, NULL, ?)",
                           (request_id, key, int(succeeded)))
            return succeeded
