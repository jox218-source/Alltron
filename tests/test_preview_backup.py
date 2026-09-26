from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock
import zipfile

from tools import preview_backup, preview_install
from src.alltron.timers import TimerStore
import test_preview_install


class PreviewBackupTests(unittest.TestCase):
    """Exercise backups against real install fixtures and TimerStore's schema."""

    def setUp(self):
        self.fixture = test_preview_install.PreviewInstallTests()
        self.fixture.setUp()
        self.root = self.fixture.root
        preview_install.initialize(self.root)
        self.fixture.install_fixture("1.0.0")
        self.db = self.root / "data" / "timers.sqlite3"
        self.store = TimerStore(self.db)

    def tearDown(self):
        self.fixture.tearDown()

    def add_timer(self, label: str, *, now: float = 1000) -> dict:
        return self.store.add(90, label, now=now, request_id="request-" + label)

    def timer_labels(self) -> list[str]:
        database = sqlite3.connect(self.db)
        try:
            return [row[0] for row in database.execute("SELECT label FROM timers ORDER BY label")]
        finally:
            database.close()

    def test_restore_roundtrip_makes_safety_copy_and_keeps_later_data(self):
        self.add_timer("Before snapshot")
        snapshot = preview_install.backup(self.root)
        self.add_timer("Added later", now=1100)

        result = preview_install.restore(self.root, snapshot["id"], replace_data=True)

        self.assertEqual(result["status"], "restored")
        self.assertEqual(self.timer_labels(), ["Before snapshot"])
        safety = result["safety_backup"]
        self.assertEqual(safety["kind"], "snapshot")
        self.assertEqual(safety["release_sha256"], snapshot["release_sha256"])
        listed = {item["id"]: item for item in preview_install.backups(self.root)["backups"]}
        self.assertEqual(listed[safety["id"]]["kind"], "snapshot")
        _, payload = preview_backup.read_archive(self.root / "backups" / (safety["id"] + ".zip"), safety["id"])
        with tempfile.TemporaryDirectory() as directory:
            saved_path = Path(directory) / "fixture.sqlite3"
            saved_path.write_bytes(payload)
            saved = sqlite3.connect(saved_path)
            try:
                labels = [row[0] for row in saved.execute("SELECT label FROM timers ORDER BY label")]
            finally:
                saved.close()
        self.assertEqual(labels, ["Added later", "Before snapshot"])

    def test_restore_requires_explicit_replace_data(self):
        snapshot = preview_install.backup(self.root)
        before = self.db.read_bytes()
        with self.assertRaisesRegex(preview_install.InstallError, "--replace-data"):
            preview_install.restore(self.root, snapshot["id"])
        self.assertEqual(self.db.read_bytes(), before)

    def test_restore_requires_exact_current_release(self):
        snapshot = preview_install.backup(self.root)
        self.fixture.install_fixture("1.1.0")
        before_state = preview_install.status(self.root)
        before_data = self.db.read_bytes()
        with self.assertRaisesRegex(preview_install.InstallError, "exact release"):
            preview_install.restore(self.root, snapshot["id"], replace_data=True)
        self.assertEqual(preview_install.status(self.root), before_state)
        self.assertEqual(self.db.read_bytes(), before_data)

    def test_archive_hash_tamper_is_rejected_without_changing_database(self):
        self.add_timer("Keep intact")
        snapshot = preview_install.backup(self.root)
        archive_path = self.root / "backups" / (snapshot["id"] + ".zip")
        with zipfile.ZipFile(archive_path) as source:
            entries = {entry.filename: source.read(entry.filename) for entry in source.infolist()}
        damaged = bytearray(entries["timers.sqlite3"])
        damaged[-1] ^= 1
        entries["timers.sqlite3"] = bytes(damaged)
        with zipfile.ZipFile(archive_path, "w") as target:
            for name, data in entries.items():
                target.writestr(name, data)
        before = self.db.read_bytes()
        with self.assertRaisesRegex(preview_backup.BackupError, "checksum"):
            preview_install.restore(self.root, snapshot["id"], replace_data=True)
        self.assertEqual(self.db.read_bytes(), before)

    def test_sidecar_blocks_restore(self):
        snapshot = preview_install.backup(self.root)
        self.add_timer("Current")
        before = self.db.read_bytes()
        sidecar = self.db.with_name(self.db.name + "-wal")
        sidecar.write_bytes(b"fictional active writer")
        try:
            with self.assertRaisesRegex(preview_install.InstallError, "sidecars"):
                preview_install.restore(self.root, snapshot["id"], replace_data=True)
            self.assertEqual(self.db.read_bytes(), before)
        finally:
            sidecar.unlink()

    def test_corrupt_current_is_preserved_as_original_and_not_restorable(self):
        self.db.write_bytes(b"fictional corrupt sqlite bytes")
        installed = self.fixture.install_fixture("1.1.0")
        original = installed["data_backup"]
        self.assertEqual(original["kind"], "preserved-original")
        self.assertEqual(len(preview_install.backups(self.root)["backups"]), 1)
        with self.assertRaisesRegex(preview_install.InstallError, "recovery material"):
            preview_install.restore(self.root, original["id"], replace_data=True)
        self.assertEqual(self.db.read_bytes(), b"fictional corrupt sqlite bytes")

    def test_install_and_rollback_take_automatic_snapshots(self):
        self.add_timer("Data before update")
        update = self.fixture.install_fixture("1.1.0")
        self.assertEqual(update["data_backup"]["kind"], "snapshot")
        self.add_timer("Data before rollback", now=1200)
        rollback = preview_install.rollback(self.root)
        self.assertEqual(rollback["data_backup"]["kind"], "snapshot")
        self.assertEqual(preview_install.status(self.root)["current"]["version"], "1.0.0")

    def test_snapshot_failure_prevents_install_and_rollback_pointer_change(self):
        self.add_timer("Still valid")
        before = preview_install.status(self.root)
        archive, digest = self.fixture.make_archive("1.1.0")
        with mock.patch.object(preview_install, "preserve_before_switch", side_effect=preview_backup.BackupError("fixture snapshot failure")):
            with self.assertRaisesRegex(preview_backup.BackupError, "snapshot failure"):
                preview_install.install(self.root, archive, digest)
        self.assertEqual(preview_install.status(self.root), before)
        self.fixture.install_fixture("1.1.0")
        current = preview_install.status(self.root)
        with mock.patch.object(preview_install, "preserve_before_switch", side_effect=preview_backup.BackupError("fixture snapshot failure")):
            with self.assertRaisesRegex(preview_backup.BackupError, "snapshot failure"):
                preview_install.rollback(self.root)
        self.assertEqual(preview_install.status(self.root), current)

    def test_lock_excludes_backup_and_restore(self):
        snapshot = preview_install.backup(self.root)
        with preview_install.locked(self.root):
            with self.assertRaisesRegex(preview_install.InstallError, "busy"):
                preview_install.backup(self.root)
            with self.assertRaisesRegex(preview_install.InstallError, "busy"):
                preview_install.restore(self.root, snapshot["id"], replace_data=True)

    def test_restore_can_recover_corrupt_current_and_preserves_raw_bytes(self):
        self.add_timer("Recoverable timer")
        snapshot = preview_install.backup(self.root)
        damaged = b"fictional damaged database"
        self.db.write_bytes(damaged)
        result = preview_install.restore(self.root, snapshot["id"], replace_data=True)
        self.assertEqual(self.timer_labels(), ["Recoverable timer"])
        safety = result["safety_backup"]
        metadata, content = preview_backup.read_archive(self.root / "backups" / (safety["id"] + ".zip"), safety["id"])
        self.assertEqual(metadata["kind"], "preserved-original")
        self.assertEqual(content, damaged)

    def test_failed_safety_copy_prevents_restore(self):
        snapshot = preview_install.backup(self.root)
        self.add_timer("Retain current")
        before = self.db.read_bytes()
        with mock.patch.object(preview_backup, "write_archive", side_effect=OSError("fictional disk failure")):
            with self.assertRaises(OSError):
                preview_install.restore(self.root, snapshot["id"], replace_data=True)
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(list(self.db.parent.glob(".restore-*")), [])

    def test_valid_checksum_with_invalid_database_is_not_restored(self):
        self.add_timer("Retain current")
        before = self.db.read_bytes()
        release = preview_install.load_state(self.root)["current"]
        folder = preview_install.backup_directory(self.root, create=True)
        forged = preview_backup.write_archive(folder, b"not a SQLite database", release, "snapshot")
        with self.assertRaises(preview_backup.InvalidDatabase):
            preview_install.restore(self.root, forged["id"], replace_data=True)
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(len(preview_install.backups(self.root)["backups"]), 1)

    def test_linked_backup_is_not_read_or_restored(self):
        snapshot = preview_install.backup(self.root)
        source = self.root / "backups" / (snapshot["id"] + ".zip")
        duplicate = self.fixture.base / "linked.zip"
        os.link(source, duplicate)
        before = self.db.read_bytes()
        with self.assertRaisesRegex(preview_install.InstallError, "links"):
            preview_install.restore(self.root, snapshot["id"], replace_data=True)
        self.assertEqual(self.db.read_bytes(), before)

    def test_snapshot_includes_committed_wal_data(self):
        database = sqlite3.connect(self.db)
        try:
            database.execute("PRAGMA journal_mode=WAL")
            database.execute(
                "INSERT INTO timers(id,label,created_at,due_at,state,request_id) VALUES(?,?,?,?,?,?)",
                ("wal-fixture", "Committed WAL", 10.0, 20.0, "running", "wal-request"),
            )
            database.commit()
            self.assertTrue(self.db.with_name(self.db.name + "-wal").exists())
            snapshot = preview_install.backup(self.root)
            _, payload = preview_backup.read_archive(self.root / "backups" / (snapshot["id"] + ".zip"), snapshot["id"])
            with tempfile.TemporaryDirectory() as directory:
                saved_path = Path(directory) / "fixture.sqlite3"
                saved_path.write_bytes(payload)
                saved = sqlite3.connect(saved_path)
                try:
                    row = saved.execute("SELECT label FROM timers WHERE id='wal-fixture'").fetchone()
                finally:
                    saved.close()
        finally:
            database.close()
        self.assertEqual(row, ("Committed WAL",))

    def test_restore_clean_wal_database_never_replaces_with_sidecars(self):
        self.add_timer("Original")
        snapshot = preview_install.backup(self.root)
        self.add_timer("Keep if blocked")
        database = sqlite3.connect(self.db)
        try:
            database.execute("PRAGMA journal_mode=WAL")
        finally:
            database.close()
        self.assertFalse(self.db.with_name(self.db.name + "-wal").exists())
        before = self.db.read_bytes()
        try:
            preview_install.restore(self.root, snapshot["id"], replace_data=True)
        except preview_install.InstallError as error:
            self.assertIn("sidecars", str(error))
            self.assertEqual(self.db.read_bytes(), before)
        else:
            # SQLite platforms that remove their read-only sidecars may finish.
            self.assertFalse(self.db.with_name(self.db.name + "-wal").exists())
            self.assertFalse(self.db.with_name(self.db.name + "-shm").exists())
            self.assertEqual(self.timer_labels(), ["Original"])

    def test_unsupported_database_schema_is_rejected(self):
        database = sqlite3.connect(self.db)
        try:
            database.execute("CREATE TABLE fictional_extra(value TEXT)")
        finally:
            database.close()
        with self.assertRaises(preview_backup.InvalidDatabase):
            preview_install.backup(self.root)

    def test_internal_schema_prefix_is_literal(self):
        database = sqlite3.connect(self.db)
        try:
            database.execute("CREATE TABLE sqliteXfixture(value TEXT)")
        finally:
            database.close()
        with self.assertRaises(preview_backup.InvalidDatabase):
            preview_install.backup(self.root)

    def test_missing_or_changed_unique_index_is_rejected(self):
        database = sqlite3.connect(self.db)
        try:
            database.execute("DROP INDEX timers_request_id")
            database.commit()
            with self.assertRaises(preview_backup.InvalidDatabase):
                preview_install.backup(self.root)
            database.execute("CREATE INDEX timers_request_id ON timers(request_id)")
            database.commit()
            with self.assertRaises(preview_backup.InvalidDatabase):
                preview_install.backup(self.root)
        finally:
            database.close()

    @unittest.skipUnless(os.name == "posix", "POSIX mode assertions")
    def test_backup_directory_and_archive_are_owner_only(self):
        snapshot = preview_install.backup(self.root)
        folder = self.root / "backups"
        archive = folder / (snapshot["id"] + ".zip")
        self.assertEqual(folder.stat().st_mode & 0o777, 0o700)
        self.assertEqual(archive.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
