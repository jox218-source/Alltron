"""Bounded local SQLite snapshots. Callers must hold the managed preview lock."""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import tempfile
import time
from uuid import uuid4
import zipfile

MAX_DATABASE = 64 * 1024 * 1024
FORMAT = "alltron-data-backup-1"
IDENTITY = re.compile(r"[0-9a-f]{32}")
DIGEST = re.compile(r"[0-9a-f]{64}")
# Deliberately accept only the public preview schema, including its constraints.
# Schema changes require an explicit recovery/migration design before acceptance.
SCHEMA = {
    ("table", "timers"): "CREATE TABLE timers (id TEXT PRIMARY KEY, label TEXT NOT NULL, "
        "created_at REAL NOT NULL, due_at REAL NOT NULL, state TEXT NOT NULL "
        "CHECK (state IN ('running', 'cancelled', 'done')), request_id TEXT)",
    ("index", "timers_request_id"): "CREATE UNIQUE INDEX timers_request_id ON timers(request_id)",
    ("table", "alarms"): "CREATE TABLE alarms (id TEXT PRIMARY KEY, label TEXT NOT NULL, "
        "created_at REAL NOT NULL, due_at REAL NOT NULL, state TEXT NOT NULL "
        "CHECK (state IN ('running', 'cancelled', 'done')), request_id TEXT UNIQUE, delivery TEXT DEFAULT 'pending')",
    ("table", "shopping_items"): "CREATE TABLE shopping_items (id TEXT PRIMARY KEY, text TEXT NOT NULL, "
        "item_key TEXT NOT NULL, created_at REAL NOT NULL, done INTEGER NOT NULL DEFAULT 0 CHECK (done IN (0, 1)))",
    ("index", "shopping_open_key"): "CREATE UNIQUE INDEX shopping_open_key ON shopping_items(item_key) WHERE done = 0",
    ("table", "shopping_requests"): "CREATE TABLE shopping_requests (request_id TEXT PRIMARY KEY, "
        "action TEXT NOT NULL, item_key TEXT NOT NULL, item_id TEXT, succeeded INTEGER NOT NULL CHECK (succeeded IN (0, 1)))",
}


class BackupError(Exception):
    pass


class InvalidDatabase(BackupError):
    pass


def readonly(path: Path) -> sqlite3.Connection:
    database = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=1)
    database.execute("PRAGMA trusted_schema=OFF")
    deadline = time.monotonic() + 5
    database.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
    return database


def validate_database(path: Path) -> None:
    if not 0 < path.stat().st_size <= MAX_DATABASE:
        raise InvalidDatabase("Database is empty or exceeds the preview backup limit")
    try:
        with closing(readonly(path)) as database:
            objects = database.execute("SELECT type, name, sql FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'").fetchall()
            actual = {(kind, name): " ".join((sql or "").split()) for kind, name, sql in objects}
            if actual != SCHEMA:
                raise InvalidDatabase("Database does not match the supported preview schema")
            if database.execute("PRAGMA integrity_check").fetchmany(2) != [("ok",)]:
                raise InvalidDatabase("Database integrity check failed")
    except sqlite3.DatabaseError as error:
        if getattr(error, "sqlite_errorcode", 0) & 255 in (sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB):
            raise InvalidDatabase("Database integrity check failed") from None
        raise BackupError("Database could not be checked; stop other database users and retry") from None


def bounded_read(path: Path) -> bytes:
    with path.open("rb") as stream:
        content = stream.read(MAX_DATABASE + 1)
    if len(content) > MAX_DATABASE:
        raise BackupError("Database exceeds the 64 MiB preview backup limit")
    return content


def write_archive(folder: Path, database: bytes, release: str, kind: str) -> dict:
    if not DIGEST.fullmatch(release) or kind not in ("snapshot", "preserved-original"):
        raise BackupError("Invalid backup identity")
    identity = uuid4().hex
    metadata = {"format": FORMAT, "id": identity, "kind": kind,
                "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "release_sha256": release, "database_size": len(database),
                "database_sha256": hashlib.sha256(database).hexdigest()}
    target = folder / (identity + ".zip")
    if target.exists():
        raise BackupError("Backup identity collision; retry the operation")
    if shutil.disk_usage(folder).free < len(database) + 1024 * 1024:
        raise BackupError("Free more disk space before creating a backup")
    with tempfile.NamedTemporaryFile(dir=folder, prefix=".backup-", delete=False) as stream:
        temporary = Path(stream.name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, payload in (("backup.json", json.dumps(metadata, sort_keys=True).encode()), ("timers.sqlite3", database)):
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = 0o100600 << 16
                archive.writestr(info, payload)
        with temporary.open("r+b") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        sync_directory(folder)
    finally:
        temporary.unlink(missing_ok=True)
    return metadata


def sync_directory(folder: Path) -> None:
    if os.name == "posix":
        descriptor = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def create_snapshot(database: Path, folder: Path, release: str) -> dict:
    validate_database(database)
    if shutil.disk_usage(folder).free < 2 * database.stat().st_size + 8 * 1024 * 1024:
        raise BackupError("Free more disk space before creating a backup")
    try:
        with tempfile.TemporaryDirectory(dir=folder, prefix=".snapshot-") as directory:
            snapshot = Path(directory) / "timers.sqlite3"
            descriptor = os.open(snapshot, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
            deadline = time.monotonic() + 10

            def progress(status, remaining, total):
                if time.monotonic() > deadline:
                    raise BackupError("Database backup timed out; stop other database users and retry")
                if snapshot.stat().st_size > MAX_DATABASE:
                    raise BackupError("Database exceeds the 64 MiB preview backup limit")

            with closing(readonly(database)) as source, closing(sqlite3.connect(snapshot)) as destination:
                source.backup(destination, pages=256, progress=progress, sleep=0.05)
                destination.execute("PRAGMA journal_mode=DELETE")
            validate_database(snapshot)
            return write_archive(folder, bounded_read(snapshot), release, "snapshot")
    except sqlite3.DatabaseError:
        raise BackupError("Database snapshot failed; the selected release and data are unchanged") from None


def read_archive(path: Path, identity: str) -> tuple[dict, bytes]:
    if not IDENTITY.fullmatch(identity):
        raise BackupError("Choose a backup ID from the backups command")
    try:
        with path.open("rb") as stream:
            content = stream.read(MAX_DATABASE + 65537)
        if len(content) > MAX_DATABASE + 65536:
            raise BackupError("Backup archive exceeds the preview size limit")
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if sorted(archive.namelist()) != ["backup.json", "timers.sqlite3"]:
                raise BackupError("Backup archive has an unexpected inventory")
            for info in archive.infolist():
                limit = 8192 if info.filename == "backup.json" else MAX_DATABASE
                if (info.file_size > limit or info.flag_bits & 1
                        or stat.S_IFMT(info.external_attr >> 16) not in (0, stat.S_IFREG)
                        or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
                    raise BackupError("Backup archive contains an unsupported entry")
            metadata = json.loads(archive.read("backup.json"))
            fields = {"format", "id", "kind", "created_at", "release_sha256", "database_size", "database_sha256"}
            if (not isinstance(metadata, dict) or set(metadata) != fields or metadata["format"] != FORMAT
                    or metadata["id"] != identity or metadata["kind"] not in ("snapshot", "preserved-original")
                    or not isinstance(metadata["created_at"], str)
                    or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", metadata["created_at"])
                    or not isinstance(metadata["release_sha256"], str) or not DIGEST.fullmatch(metadata["release_sha256"])
                    or type(metadata["database_size"]) is not int or not 0 <= metadata["database_size"] <= MAX_DATABASE
                    or not isinstance(metadata["database_sha256"], str) or not DIGEST.fullmatch(metadata["database_sha256"])):
                raise BackupError("Backup metadata is invalid")
            database = archive.read("timers.sqlite3")
            if len(database) != metadata["database_size"] or hashlib.sha256(database).hexdigest() != metadata["database_sha256"]:
                raise BackupError("Backup checksum does not match; the database is unchanged")
            return metadata, database
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, zipfile.BadZipFile, NotImplementedError):
        raise BackupError("Backup cannot be read or validated; the database is unchanged") from None
