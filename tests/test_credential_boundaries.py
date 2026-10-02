"""Synthetic fixtures for private-file and CLI credential boundaries."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from alltron.answers import CodexAnswers, CodexCLIRunner
from alltron.private_files import read_private_text


class PrivateTextBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        if os.name == "posix":
            self.root.chmod(0o700)

    def tearDown(self):
        self.temp.cleanup()

    def private_file(self, name="note.txt", content=b"fictional private fixture\n"):
        path = self.root / name
        path.write_bytes(content)
        if os.name == "posix":
            path.chmod(0o600)
        return path

    def test_reads_owner_private_absolute_regular_text(self):
        path = self.private_file()
        self.assertEqual(read_private_text(path, 1024), "fictional private fixture\n")

    def test_rejects_relative_directory_oversize_and_invalid_utf8(self):
        path = self.private_file()
        with self.assertRaises(ValueError):
            read_private_text(Path("relative-fixture.txt"), 1024)
        with self.assertRaises(ValueError):
            read_private_text(self.root, 1024)
        with self.assertRaises(ValueError):
            read_private_text(path, 2)
        invalid = self.private_file("invalid.txt", b"\xff\xfe")
        with self.assertRaises(ValueError):
            read_private_text(invalid, 1024)

    def test_rejects_any_git_repository_path(self):
        repo = self.root / "fictional-repo"
        repo.mkdir()
        (repo / ".git").mkdir()
        path = repo / "private.txt"
        path.write_text("fictional", encoding="utf-8")
        if os.name == "posix":
            path.chmod(0o600)
        with self.assertRaises(ValueError):
            read_private_text(path, 1024)

    def test_rejects_hardlinks_and_linked_ancestors(self):
        original = self.private_file()
        hardlink = self.root / "hardlink.txt"
        try:
            os.link(original, hardlink)
        except (OSError, NotImplementedError):
            self.skipTest("hardlinks are unavailable in this environment")
        with self.assertRaises(ValueError):
            read_private_text(hardlink, 1024)

        real_parent = self.root / "real-parent"
        real_parent.mkdir()
        nested = real_parent / "nested.txt"
        nested.write_text("fictional", encoding="utf-8")
        if os.name == "posix":
            nested.chmod(0o600)
        linked_parent = self.root / "linked-parent"
        try:
            linked_parent.symlink_to(real_parent, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("directory symlinks are unavailable in this environment")
        with self.assertRaises(ValueError):
            read_private_text(linked_parent / nested.name, 1024)

    @unittest.skipUnless(os.name == "posix", "POSIX owner-private modes are platform-specific")
    def test_rejects_file_or_parent_with_nonprivate_posix_permissions(self):
        path = self.private_file()
        path.chmod(0o644)
        with self.assertRaises(ValueError):
            read_private_text(path, 1024)
        path.chmod(0o600)
        self.root.chmod(0o755)
        with self.assertRaises(ValueError):
            read_private_text(path, 1024)


class CodexRunnerBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.work = self.root / "work"
        self.profile = self.root / "isolated-profile"
        self.home = self.root / "isolated-home"
        self.work.mkdir()
        self.profile.mkdir()
        self.home.mkdir()
        if os.name == "posix":
            self.root.chmod(0o700)
            for directory in (self.work, self.profile, self.home):
                directory.chmod(0o700)

    def tearDown(self):
        self.temp.cleanup()

    def fake_cli(self, body, name="fake_cli.py"):
        path = self.root / name
        path.write_text("import sys\n" + body, encoding="utf-8")
        return (sys.executable, str(path))

    def runner(self, launcher=None):
        return CodexCLIRunner(launcher or self.fake_cli("print('fictional answer')\n"),
                              self.work, self.profile, self.home)

    def test_accepts_separate_isolated_absolute_directories(self):
        result = CodexAnswers(self.runner()).answer("Why is the sky blue?")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["text"], "fictional answer")

    def test_refuses_overlapping_and_default_profile_directories(self):
        nested = self.work / "nested-profile"
        nested.mkdir()
        with self.assertRaises(ValueError):
            CodexCLIRunner(self.fake_cli("pass\n"), self.work, nested, self.home)
        child_home = self.profile / "child"
        child_home.mkdir()
        with self.assertRaises(ValueError):
            CodexCLIRunner(self.fake_cli("pass\n"), self.work, self.profile, child_home)

        fake_default_home = self.root / "synthetic-owner-home"
        default_profile = fake_default_home / ".codex"
        fake_default_home.mkdir()
        default_profile.mkdir()
        with mock.patch("pathlib.Path.home", return_value=fake_default_home):
            with self.assertRaises(ValueError):
                CodexCLIRunner(self.fake_cli("pass\n"), self.work, default_profile, self.home)

    def test_refuses_directory_paths_inside_git_or_through_symlink(self):
        repo = self.root / "fictional-repo"
        repo.mkdir()
        (repo / ".git").mkdir()
        work = repo / "work"
        profile = repo / "profile"
        home = repo / "home"
        for directory in (work, profile, home):
            directory.mkdir()
        with self.assertRaises(ValueError):
            CodexCLIRunner(self.fake_cli("pass\n"), work, profile, home)

        alias = self.root / "work-alias"
        try:
            alias.symlink_to(self.work, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("directory symlinks are unavailable in this environment")
        with self.assertRaises(ValueError):
            CodexCLIRunner(self.fake_cli("pass\n"), alias, self.profile, self.home)

    def test_rejects_question_outside_string_and_length_bounds(self):
        runner = self.runner()
        for question in (None, 42, "", "q" * 501):
            with self.subTest(question_type=type(question).__name__):
                with self.assertRaises(ValueError):
                    runner(question)

    def test_subprocess_does_not_inherit_credential_environment(self):
        launcher = self.fake_cli(
            "import os\n"
            "names = ('OPENAI_API_KEY', 'CODEX_ACCESS_TOKEN', 'ALLTRON_HA_CONFIG')\n"
            "print('|'.join(name for name in names if name in os.environ))\n")
        names = ("OPENAI_API_KEY", "CODEX_ACCESS_TOKEN", "ALLTRON_HA_CONFIG")
        supplied = dict(zip(names, ("fictional-key", "fictional-token", "fictional-config-path")))
        with mock.patch.dict(os.environ, supplied, clear=False):
            self.assertEqual(self.runner(launcher)("Why?").strip(), "")

    def test_output_budget_combines_stdout_and_stderr_and_answers_fail_closed(self):
        oversized_stdout = self.runner(self.fake_cli("sys.stdout.write('x' * 65537)\n"))
        oversized_stderr = self.runner(self.fake_cli("sys.stderr.write('x' * 65537)\n"))
        combined = self.runner(self.fake_cli("sys.stdout.write('x' * 40000)\n"
                                             "sys.stderr.write('y' * 25537)\n"))
        for runner in (oversized_stdout, oversized_stderr, combined):
            with self.subTest(launcher=runner.launcher[-1]):
                with mock.patch("alltron.answers.MAX_OUTPUT_BYTES", 65536):
                    result = CodexAnswers(runner).answer("Why?")
                self.assertEqual(result["status"], "unavailable")
                self.assertNotIn("xxxx", result["text"])

    def test_deadline_maps_to_bounded_timeout_answer(self):
        runner = self.runner(self.fake_cli("sys.stdin.read()\n"
                                           "import time\ntime.sleep(10)\n"))
        with mock.patch("alltron.answers.TIMEOUT_SECONDS", 0.2):
            result = CodexAnswers(runner).answer("Why?")
        self.assertEqual(result["status"], "timeout")
        self.assertEqual(result["text"], "The answer service timed out.")

    @unittest.skipUnless(os.name == "posix", "process-group cleanup assertion is POSIX-specific")
    def test_timeout_cleans_up_descendant_process(self):
        marker = self.root / "descendant-marker.txt"
        child_code = "import time; time.sleep(0.8); open(%r, 'w').write('late')" % str(marker)
        launcher = self.fake_cli(
            "import subprocess, time\n"
            "subprocess.Popen([sys.executable, '-c', %r])\n"
            "time.sleep(10)\n" % child_code)
        with mock.patch("alltron.answers.TIMEOUT_SECONDS", 0.2):
            with self.assertRaises(subprocess.TimeoutExpired):
                self.runner(launcher)("Why?")
        time.sleep(1.0)
        self.assertFalse(marker.exists(), "timed-out CLI descendant survived its runner")


if __name__ == "__main__":
    unittest.main()
