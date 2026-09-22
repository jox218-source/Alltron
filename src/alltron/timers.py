"""Durable local timer state. No household or account data is required."""

from __future__ import annotations

import sqlite3
import time
import uuid
import os
import stat
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

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def add(self, seconds: int, label: str = "Timer", *, now: float | None = None) -> dict:
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
        }
        with self._connect() as db:
            db.execute(
                "INSERT INTO timers (id, label, created_at, due_at, state) VALUES (:id, :label, :created_at, :due_at, :state)",
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
