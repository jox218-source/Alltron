"""Synthetic local-inventory tests; every fixture contains invented data."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock
import zipfile
from pathlib import Path

from tools.credential_audit import audit_local


class LocalCredentialAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()

    def tearDown(self):
        self.temp.cleanup()

    def fixture_root(self, name):
        root = self.base / name
        root.mkdir()
        return root

    @unittest.skipUnless(os.name == "posix", "Linux mount inventory only")
    def test_rejects_a_mount_at_the_root_before_reading_files(self):
        root = self.fixture_root("mount-root")
        mount_row = f"1 0 0:1 / {root} rw - tmpfs tmpfs rw\n"
        with mock.patch.object(Path, "read_text", return_value=mount_row):
            problems, count = audit_local(root)
        self.assertEqual(count, 0)
        self.assertIn("Filesystem mount at or below audit root requires separate review", problems)

    def test_rejects_ignored_auth_and_profile_paths(self):
        root = self.fixture_root("ignored-paths")
        (root / ".gitignore").write_text("auth.json\n.codex/\n", encoding="utf-8")
        (root / "auth.json").write_text("synthetic placeholder only\n", encoding="utf-8")
        profile = root / ".codex"
        profile.mkdir()
        (profile / "notes.txt").write_text("fictional profile fixture\n", encoding="utf-8")

        problems, _count = audit_local(root)

        self.assertIn("Credential/profile/private path present in repository", problems)

    def test_rejects_external_hardlink(self):
        root = self.fixture_root("hardlink")
        outside = self.base / "fictional-source.txt"
        outside.write_text("invented fixture text\n", encoding="utf-8")
        try:
            os.link(outside, root / "ordinary-name.txt")
        except (OSError, NotImplementedError):
            self.skipTest("hardlinks are unavailable in this environment")

        problems, _count = audit_local(root)

        self.assertIn("Local nonregular or hardlinked file requires review", problems)

    def test_rejects_symlink_without_following_target(self):
        root = self.fixture_root("symlink")
        target = self.base / "fictional-target.txt"
        target.write_text("invented fixture text\n", encoding="utf-8")
        link = root / "ordinary-name.txt"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("file symlinks are unavailable in this environment")

        problems, count = audit_local(root)

        self.assertIn("Local link or reparse point requires review", problems)
        self.assertEqual(count, 0)

    def test_detects_sensitive_pattern_in_gitignored_innocuous_text(self):
        root = self.fixture_root("ignored-content")
        (root / ".gitignore").write_text("harmless.txt\n", encoding="utf-8")
        invented_address = b"fictional-person" + b"@" + b"example.invalid"
        (root / "harmless.txt").write_bytes(b"Contact fixture: " + invented_address + b"\n")

        problems, _count = audit_local(root)

        self.assertIn("Possible private data in local text", problems)

    def test_rejects_archive_with_auth_json_member(self):
        root = self.fixture_root("archive")
        with zipfile.ZipFile(root / "fixture.zip", "w") as archive:
            archive.writestr("auth.json", "synthetic placeholder only")

        problems, _count = audit_local(root)

        self.assertIn("Credential/private member in local archive", problems)

    def test_genuine_invented_normal_files_pass(self):
        root = self.fixture_root("normal")
        (root / "notes.txt").write_text("A fictional public note about a desk lamp.\n", encoding="utf-8")

        problems, count = audit_local(root)

        self.assertEqual(problems, [])
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
