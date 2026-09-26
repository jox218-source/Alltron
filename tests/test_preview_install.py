from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

from tools import build_release, preview_install


SERVER = b'''import json\nfrom http.server import BaseHTTPRequestHandler, HTTPServer\n\nclass Handler(BaseHTTPRequestHandler):\n    def do_GET(self):\n        if self.path != "/api/health":\n            self.send_error(404)\n            return\n        data = {"mode": "developer-preview", "local_timers": "ready", "home_assistant": "not-configured", "codex": "not-configured"}\n        body = json.dumps(data).encode()\n        self.send_response(200)\n        self.send_header("Content-Type", "application/json")\n        self.send_header("Content-Length", str(len(body)))\n        self.end_headers()\n        self.wfile.write(body)\n    def log_message(self, *args):\n        pass\n\ndef make_server(port, store_path):\n    return HTTPServer(("127.0.0.1", port), Handler)\n'''


class PreviewInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / "preview"
        self.archive_dir = self.base / "archives"
        self.archive_dir.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def make_archive(self, version: str, server: bytes = SERVER) -> tuple[Path, str]:
        payloads = {
            "docs/RELEASE_PATHS.txt": (
                "docs/RELEASE_PATHS.txt\npyproject.toml\n"
                "src/alltron/__init__.py\nsrc/alltron/__main__.py\nsrc/alltron/server.py\n"
            ).encode(),
            "pyproject.toml": f'[project]\nname = "alltron"\nversion = "{version}"\n'.encode(),
            "src/alltron/__init__.py": b'"""Fictional preview fixture."""\n',
            "src/alltron/__main__.py": b'raise SystemExit("fixture")\n',
            "src/alltron/server.py": server,
        }
        files = [
            {"path": name, "sha256": hashlib.sha256(payload).hexdigest(), "size": len(payload)}
            for name, payload in sorted(payloads.items())
        ]
        commit = hashlib.sha1(version.encode()).hexdigest()
        manifest = {
            "schema": 1,
            "kind": "source-preview",
            "version": version,
            "commit": commit,
            "files": files,
        }
        payloads[build_release.MANIFEST] = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
        archive_path = self.archive_dir / f"fixture-{version}.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            for name, payload in sorted(payloads.items()):
                info, content = build_release.zip_entry(name, payload)
                archive.writestr(info, content)
        return archive_path, hashlib.sha256(archive_path.read_bytes()).hexdigest()

    def install_fixture(self, version: str):
        archive, digest = self.make_archive(version)
        return preview_install.install(self.root, archive, digest)

    def test_initialize_and_refuse_nonempty_folder(self):
        self.root.mkdir()
        (self.root / "user-file.txt").write_text("keep", encoding="utf-8")
        with self.assertRaises(preview_install.InstallError):
            preview_install.initialize(self.root)
        self.assertEqual((self.root / "user-file.txt").read_text(encoding="utf-8"), "keep")
        self.assertFalse((self.root / preview_install.STATE).exists())

        self.root2 = self.base / "fresh-preview"
        result = preview_install.initialize(self.root2)
        self.assertEqual(result["status"], "initialized")
        self.assertTrue((self.root2 / "releases").is_dir())
        self.assertTrue((self.root2 / "data").is_dir())

    def test_preflight_is_read_only(self):
        before = set(self.base.iterdir())
        result = preview_install.preflight(self.root)
        self.assertTrue(result["ready"], result)
        self.assertFalse(result["appliance_ready"])
        self.assertEqual(set(self.base.iterdir()), before)
        self.assertFalse(self.root.exists())

    def test_status_does_not_modify_unrecognized_folder(self):
        self.root.mkdir(mode=0o700)
        (self.root / "keep.txt").write_bytes(b"Fictional data")
        before = set(self.root.iterdir())
        with self.assertRaises(preview_install.InstallError):
            preview_install.status(self.root)
        self.assertEqual(set(self.root.iterdir()), before)

    def test_restricted_process_does_not_need_a_home_directory(self):
        with mock.patch.object(Path, "home", side_effect=RuntimeError("No home in isolated environment")):
            self.assertEqual(preview_install.checked_root(self.root), self.root)

    @unittest.skipUnless(os.name == "posix", "POSIX symlink fixture")
    def test_root_symlink_is_refused_without_modifying_target(self):
        target = self.base / "unrelated"
        target.mkdir(mode=0o700)
        self.root.symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(preview_install.InstallError, "links"):
            preview_install.initialize(self.root)
        self.assertEqual(list(target.iterdir()), [])

    def test_install_repeat_update_and_rollback(self):
        preview_install.initialize(self.root)
        owner_data = self.root / "data" / "fictional-state.txt"
        owner_data.write_bytes(b"Fictional persistent state")
        first = self.install_fixture("1.0.0")
        state_first = preview_install.status(self.root)
        self.assertEqual(state_first["current"]["version"], "1.0.0")
        self.assertIsNone(state_first["previous"])

        self.install_fixture("1.0.0")
        repeated = preview_install.status(self.root)
        self.assertEqual(repeated, state_first)

        self.install_fixture("1.1.0")
        updated = preview_install.status(self.root)
        self.assertEqual(updated["current"]["version"], "1.1.0")
        self.assertEqual(updated["previous"]["version"], "1.0.0")

        rolled = preview_install.rollback(self.root)
        self.assertEqual(rolled["status"], "rolled_back")
        after_rollback = preview_install.status(self.root)
        self.assertEqual(after_rollback["current"]["version"], "1.0.0")
        self.assertEqual(after_rollback["previous"]["version"], "1.1.0")
        self.assertEqual(first["version"], "1.0.0")
        self.assertEqual(owner_data.read_bytes(), b"Fictional persistent state")

    def test_failed_pointer_switch_can_be_retried(self):
        preview_install.initialize(self.root)
        self.install_fixture("1.0.0")
        before = preview_install.status(self.root)
        archive, digest = self.make_archive("1.1.0")
        with mock.patch.object(preview_install, "write_state", side_effect=OSError("simulated interruption")):
            with self.assertRaises(OSError):
                preview_install.install(self.root, archive, digest)
        self.assertEqual(preview_install.status(self.root), before)
        self.assertTrue((self.root / "releases" / digest).is_dir())
        preview_install.install(self.root, archive, digest)
        self.assertEqual(preview_install.status(self.root)["current"]["version"], "1.1.0")

    def test_real_startup_failure_keeps_selected_release(self):
        preview_install.initialize(self.root)
        self.install_fixture("1.0.0")
        before = preview_install.status(self.root)
        archive, digest = self.make_archive("2.0.0", b"raise RuntimeError('fictional startup failure')\n")
        with self.assertRaisesRegex(preview_install.InstallError, "health check"):
            preview_install.install(self.root, archive, digest)
        self.assertEqual(preview_install.status(self.root), before)

    def test_incorrect_sha_is_rejected(self):
        preview_install.initialize(self.root)
        archive, digest = self.make_archive("1.0.0")
        wrong = ("0" if digest[0] != "0" else "1") + digest[1:]
        with self.assertRaisesRegex(preview_install.InstallError, "checksum"):
            preview_install.install(self.root, archive, wrong)
        self.assertIsNone(preview_install.status(self.root)["current"])

    def test_failed_candidate_smoke_keeps_previous_current(self):
        preview_install.initialize(self.root)
        self.install_fixture("1.0.0")
        old = preview_install.status(self.root)
        archive, digest = self.make_archive("2.0.0")
        with mock.patch.object(preview_install, "smoke_test", side_effect=preview_install.InstallError("fixture smoke failure")):
            with self.assertRaisesRegex(preview_install.InstallError, "fixture smoke failure"):
                preview_install.install(self.root, archive, digest)
        current = preview_install.status(self.root)
        self.assertEqual(current["current"], old["current"])
        self.assertEqual(current["previous"], old["previous"])
        self.assertFalse((self.root / "releases" / digest).exists())

    def test_lock_excludes_install(self):
        preview_install.initialize(self.root)
        self.install_fixture("1.0.0")
        archive, digest = self.make_archive("1.1.0")
        with preview_install.locked(self.root):
            with self.assertRaisesRegex(preview_install.InstallError, "busy"):
                preview_install.install(self.root, archive, digest)
            with self.assertRaisesRegex(preview_install.InstallError, "busy"):
                preview_install.rollback(self.root)
        self.assertEqual(preview_install.status(self.root)["current"]["version"], "1.0.0")

    def test_tampered_installed_source_is_refused(self):
        preview_install.initialize(self.root)
        self.install_fixture("1.0.0")
        current = preview_install.status(self.root)["current"]
        source = self.root / "releases" / current["archive_sha256"] / "content" / "src" / "alltron" / "server.py"
        source.write_bytes(source.read_bytes() + b"\n# changed\n")
        with self.assertRaisesRegex(preview_install.InstallError, "changed"):
            preview_install.status(self.root)

    def test_disk_space_block_is_reported_and_prevents_install(self):
        preview_install.initialize(self.root)
        archive, digest = self.make_archive("1.0.0")
        usage = type("DiskUsage", (), {"total": 100, "used": 100, "free": 0})()
        with mock.patch.object(preview_install.shutil, "disk_usage", return_value=usage):
            result = preview_install.preflight(self.root)
            self.assertFalse(result["ready"])
            self.assertEqual(next(check for check in result["checks"] if check["code"] == "free_space")["status"], "blocked")
            with self.assertRaisesRegex(preview_install.InstallError, "Preflight is blocked"):
                preview_install.install(self.root, archive, digest)
        self.assertIsNone(preview_install.status(self.root)["current"])

    def test_child_environment_drops_alltron_python_and_proxy_variables(self):
        environment = {
            "ALLTRON_HOME_ASSISTANT_TOKEN": "fictional-token",
            "PYTHONPATH": "fictional-path",
            "HTTP_PROXY": "http://proxy.invalid",
            "SYSTEMROOT": "C:\\Windows",
            "TMP": "C:\\Temp",
        }
        with mock.patch.dict(os.environ, environment, clear=True):
            child = preview_install.child_environment()
        self.assertNotIn("ALLTRON_HOME_ASSISTANT_TOKEN", child)
        self.assertNotIn("PYTHONPATH", child)
        self.assertNotIn("HTTP_PROXY", child)
        if os.name == "nt":
            self.assertEqual(child.get("SYSTEMROOT"), "C:\\Windows")
            self.assertEqual(child.get("TMP"), "C:\\Temp")
        else:
            self.assertEqual(child, {})


if __name__ == "__main__":
    unittest.main()
