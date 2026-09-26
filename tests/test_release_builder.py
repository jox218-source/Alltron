import hashlib
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.build_release import ReleaseError, build_release, release_paths, verify_release


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


class ReleaseBuilderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "source"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.name", "Fixture")
        git(self.repo, "config", "user.email", "fixture" + "@" + "users.noreply.github.com")
        (self.repo / "docs").mkdir()
        (self.repo / "pyproject.toml").write_text('[project]\nversion = "0.1.0a0"\n', encoding="utf-8")
        (self.repo / "README.md").write_text("Invented preview\n", encoding="utf-8")
        (self.repo / "docs" / "RELEASE_PATHS.txt").write_text(
            "README.md\npyproject.toml\ndocs/RELEASE_PATHS.txt\n", encoding="utf-8"
        )
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "Synthetic source")

    def test_deterministic_manifest_and_excluded_files(self):
        first = build_release(self.repo, self.root / "one")
        second = build_release(self.repo, self.root / "two")
        self.assertEqual(hashlib.sha256(first.read_bytes()).digest(), hashlib.sha256(second.read_bytes()).digest())
        manifest = verify_release(first)
        self.assertEqual(manifest["commit"], git(self.repo, "rev-parse", "HEAD"))
        self.assertEqual([item["path"] for item in manifest["files"]],
                         ["README.md", "docs/RELEASE_PATHS.txt", "pyproject.toml"])
        with zipfile.ZipFile(first) as archive:
            self.assertEqual(sorted(archive.namelist()),
                             ["README.md", "RELEASE-MANIFEST.json", "docs/RELEASE_PATHS.txt", "pyproject.toml"])

    def test_dirty_tree_rejected_without_archiving_sensitive_file(self):
        (self.repo / "private-notes.txt").write_text("Synthetic secret", encoding="utf-8")
        with self.assertRaisesRegex(ReleaseError, "worktree changes"):
            build_release(self.repo, self.root / "out")
        self.assertFalse((self.root / "out").exists())

    def test_symlink_on_allowlist_rejected(self):
        # Git can represent the link without Windows symlink privileges.
        git(self.repo, "config", "core.symlinks", "false")
        (self.repo / "README.md").write_text("pyproject.toml", encoding="utf-8")
        oid = subprocess.check_output(
            ["git", "-C", str(self.repo), "hash-object", "-w", "--stdin"],
            input=b"pyproject.toml",
        ).decode().strip()
        git(self.repo, "update-index", "--add", "--cacheinfo", f"120000,{oid},README.md")
        git(self.repo, "commit", "-qm", "Synthetic symlink")
        with self.assertRaisesRegex(ReleaseError, "nonregular"):
            build_release(self.repo, self.root / "out")

    def test_unapproved_paths_and_tampering_rejected(self):
        for path in ("../private/file", "/absolute", "one\\other", "dup\ndup", "-option"):
            with self.assertRaises(ReleaseError, msg=path):
                release_paths(path.encode())
        target = build_release(self.repo, self.root / "out")
        tampered = self.root / "tampered.zip"
        with zipfile.ZipFile(target) as source, zipfile.ZipFile(tampered, "w") as dest:
            for name in source.namelist():
                payload = source.read(name)
                if name == "README.md":
                    payload += b"changed"
                dest.writestr(name, payload)
        with self.assertRaisesRegex(ReleaseError, "hash mismatch"):
            verify_release(tampered)


if __name__ == "__main__":
    unittest.main()
