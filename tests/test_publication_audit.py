import importlib.util
import secrets
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.publication_audit import audit_history, scan_historical_blobs, scan_text, valid_identity


class PublicationAuditTests(unittest.TestCase):
    def test_sensitive_text_is_reported_without_echoing_value(self):
        fake_email = ("person" + "@" + "example.invalid").encode()
        fake_ip = b"192" + b".168.1.2"
        fake_home = b"C:" + bytes([92]) + b"Users" + bytes([92]) + b"Example"
        problems = scan_text(fake_email + b"\n" + fake_ip + b"\n" + fake_home, "fixture")
        self.assertEqual(len(problems), 3)
        self.assertFalse(any("person" in problem or "168.1.2" in problem for problem in problems))

    def test_owner_must_use_chosen_no_reply_address(self):
        self.assertFalse(valid_identity("jox218-source", "example" + "@" + "gmail.com"))

    @unittest.skipUnless(importlib.util.find_spec("detect_secrets"), "audit extra not installed")
    def test_secret_scanner_inspects_historical_blob_content(self):
        synthetic_value = secrets.token_urlsafe(64).encode()
        content = b"api_key = \"" + synthetic_value + b"\"\n"
        findings = scan_historical_blobs([("a" * 40, "synthetic.txt", content)])
        self.assertTrue(findings)
        self.assertTrue(all(synthetic_value.decode() not in finding for finding in findings))

    def test_deleted_unapproved_file_still_fails_history_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)

            def git(*args):
                return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()

            git("init", "-q")
            git("config", "user.name", "Test")
            git("config", "user.email", "test" + "@" + "users.noreply.github.com")
            (repo / "README.md").write_text("Public fixture\n", encoding="utf-8")
            git("add", "README.md")
            git("commit", "-qm", "Base")
            base = git("rev-parse", "HEAD")
            private = repo / "secret" / "fixture.txt"
            private.parent.mkdir()
            private.write_text("Synthetic data only\n", encoding="utf-8")
            git("add", "secret/fixture.txt")
            git("commit", "-qm", "Add forbidden path")
            private.unlink()
            git("add", "-u")
            git("commit", "-qm", "Remove forbidden path")
            problems, count, _ = audit_history(repo, base, "HEAD", {"README.md"}, run_scanner=False)
            self.assertEqual(count, 2)
            self.assertTrue(any("unapproved path secret/fixture.txt" in problem for problem in problems))


if __name__ == "__main__":
    unittest.main()
