"""Fictional Linux setup tests; no host services, containers, or appliances are started."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest import mock

from alltron.owner import OwnerAuth, password_record
from alltron import setup as owner_setup
from tools import linux_install
from tls_fixtures import _openssl, make_certificate


OPENSSL = _openssl()


class LinuxInstallTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.temp = Path(self.directory.name)
        self.temp.chmod(0o700)

    def tearDown(self):
        self.directory.cleanup()

    def _profile(self):
        profile = self.temp / "fictional-owner-profile"
        profile.mkdir(mode=0o700)
        cert, key = make_certificate(profile, "alltron")
        profile.joinpath("owner.json").write_text(json.dumps({
            "format": "alltron-owner-1", **password_record("fictional-linux-test-passphrase"),
            "certificate": str(cert), "private_key": str(key),
        }), encoding="utf-8")
        profile.joinpath("owner.json").chmod(0o600)
        return profile

    def _prepared_environment(self):
        profile = self._profile()
        root = self.temp / "fictional-app"
        ha_root = self.temp / "fictional-ha"
        root.mkdir()
        content = self.temp / "fictional-release"
        (content / "tools").mkdir(parents=True)
        (content / "tools" / "linux_install.py").write_text("synthetic reviewed archive", encoding="utf-8")
        return root, profile, ha_root, content

    def test_safe_path_rejects_unit_mount_control_and_traversal_syntax(self):
        from pathlib import PurePosixPath

        for value in ("/tmp/profile%t", "/tmp/profile:mount", "/tmp/profile\nextra",
                      "/tmp/profile\tbad", "/tmp/profile\"quoted", "/tmp/../profile"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                linux_install.safe_path(PurePosixPath(value))
        self.assertEqual(str(linux_install.safe_path(PurePosixPath("/tmp/alltron-profile"))),
                         "/tmp/alltron-profile")

    def test_preflight_reports_prerequisites_without_claiming_acceptance(self):
        with mock.patch.object(linux_install.sys, "platform", "linux"), \
             mock.patch.object(linux_install.os, "name", "posix"), \
             mock.patch.object(linux_install.os, "geteuid", return_value=1000, create=True), \
             mock.patch.object(linux_install.shutil, "which", side_effect=lambda name: f"/fake/{name}"):
            result = linux_install.preflight()
        self.assertTrue(result["linux"])
        self.assertTrue(result["ordinary_user"])
        self.assertTrue(result["openssl"] and result["podman"] and result["systemctl"])
        self.assertFalse(result["live_acceptance"])
        self.assertFalse(result["codex_enabled"])

    @unittest.skipUnless(sys.platform == "linux" and OPENSSL,
                         "Linux preparation requires Linux and OpenSSL")
    def test_prepare_writes_restricted_units_and_does_not_start_services(self):
        root, profile, ha_root, content = self._prepared_environment()
        manifest = {"version": "0.1.0-fictional"}
        real_run = linux_install.subprocess.run
        with (mock.patch.object(linux_install, "safe_path", side_effect=lambda path: path),
              mock.patch.object(linux_install.shutil, "which", side_effect=lambda name: OPENSSL if name == "openssl" else f"/fake/{name}"),
              mock.patch.object(linux_install.manager, "locked", return_value=nullcontext()),
              mock.patch.object(linux_install.manager, "load_state", return_value={"current": "fictional-release-id"}),
              mock.patch.object(linux_install.manager, "release_on_disk", return_value=(content, manifest)),
              mock.patch.object(linux_install.subprocess, "run", wraps=real_run) as run):
            result = linux_install.prepare(root, profile, ha_root)
        self.assertEqual(result["status"], "prepared")
        self.assertFalse(result["services_started"])
        self.assertFalse(result["codex_enabled"])
        invoked = [str(call.args[0]) for call in run.call_args_list]
        self.assertTrue(invoked, "certificate generation should run the real OpenSSL command")
        self.assertFalse(any("/fake/podman" in command or "/fake/systemctl" in command for command in invoked))
        app_unit = (profile / "alltron.service").read_text(encoding="utf-8")
        ha_unit = (profile / "alltron-ha.service").read_text(encoding="utf-8")
        self.assertIn("IPAddressDeny=any", app_unit)
        self.assertIn("IPAddressAllow=127.0.0.1", app_unit)
        self.assertIn("RestrictAddressFamilies=AF_INET", app_unit)
        self.assertIn("MemoryMax=512M", app_unit)
        self.assertIn("TasksMax=32", app_unit)
        self.assertIn(linux_install.HA_IMAGE, ha_unit)
        self.assertIn("--pull=never", ha_unit)
        self.assertIn("--cap-drop=ALL", ha_unit)
        self.assertIn("--security-opt=no-new-privileges", ha_unit)
        self.assertIn("--pids-limit=256", ha_unit)
        self.assertIn("--memory=2g", ha_unit)
        self.assertIn("--publish=127.0.0.1:8123:8123", ha_unit)
        self.assertTrue((profile / "owner.json").is_file())
        self.assertTrue((ha_root / "ha.crt").is_file())
        self.assertTrue((ha_root / "ha.key").is_file())
        self.assertTrue((ha_root / "ha.key").read_text(encoding="utf-8").startswith("-----BEGIN "))

    @unittest.skipUnless(OPENSSL and os.name == "posix", "POSIX owner enrollment requires OpenSSL")
    def test_enrollment_creates_valid_tls_profile_and_repeat_preserves_it(self):
        if os.geteuid() == 0:
            self.skipTest("Owner enrollment intentionally refuses root")
        profile = self.temp / "enrolled-profile"
        result = owner_setup.enroll(profile, "fictional-enrollment-passphrase", openssl=OPENSSL)
        self.assertEqual(result["status"], "enrolled")
        auth = OwnerAuth(profile / "owner.json")
        context = auth.context()
        self.assertEqual(context.minimum_version.name, "TLSv1_2")
        cert_before = (profile / "alltron.crt").read_bytes()
        key_before = (profile / "alltron.key").read_bytes()
        self.assertEqual(owner_setup.enroll(profile, "different-fictional-passphrase", openssl=OPENSSL)["status"],
                         "already-enrolled")
        self.assertEqual((profile / "alltron.crt").read_bytes(), cert_before)
        self.assertEqual((profile / "alltron.key").read_bytes(), key_before)

    @unittest.skipUnless(os.name == "posix", "POSIX enrollment boundary")
    def test_openssl_failure_leaves_no_published_profile(self):
        if os.geteuid() == 0:
            self.skipTest("Owner enrollment intentionally refuses root")
        profile = self.temp / "failed-enrollment"
        with mock.patch.object(owner_setup.subprocess, "run", return_value=mock.Mock(returncode=1)):
            with self.assertRaisesRegex(ValueError, "TLS generation failed"):
                owner_setup.enroll(profile, "fictional-enrollment-passphrase", openssl=OPENSSL or "/fake/openssl")
        self.assertFalse(profile.exists())
        self.assertFalse(list(self.temp.glob(".alltron-enroll-*")))

    def test_overlapping_roots_are_rejected_before_archive_or_service_work(self):
        root = self.temp / "fictional-app"
        profile = self.temp / "fictional-profile"
        root.mkdir()
        profile.mkdir()
        with (mock.patch.object(linux_install, "user"),
              mock.patch.object(linux_install, "safe_path", side_effect=lambda path: path),
              mock.patch.object(linux_install.manager, "locked", return_value=nullcontext()) as locked,
              mock.patch.object(linux_install.manager, "load_state") as load_state):
            with self.assertRaisesRegex(ValueError, "separate"):
                linux_install.prepare(root, profile, root / "nested-ha")
        locked.assert_not_called()
        load_state.assert_not_called()

    def test_failed_activation_has_no_service_command(self):
        profile = self._profile()
        (profile / "services.json").write_text(json.dumps({"format": "alltron-services-1"}), encoding="utf-8")
        (profile / "services.json").chmod(0o600)
        with (mock.patch.object(linux_install, "user"),
              mock.patch.object(linux_install, "safe_path", side_effect=lambda path: path),
              mock.patch.object(linux_install.shutil, "which", return_value="/fake/systemctl"),
              mock.patch.object(linux_install.subprocess, "run") as run):
            with self.assertRaisesRegex(ValueError, "remains gated"):
                linux_install.service(profile, "activate")
        run.assert_not_called()

    def test_uninstall_preserves_unrecognized_service_file(self):
        profile = self._profile()
        (profile / "services.json").write_text(json.dumps({"format": "alltron-services-1"}), encoding="utf-8")
        (profile / "services.json").chmod(0o600)
        (profile / "alltron.service").write_text("[Unit]\nDescription=Expected Alltron\n", encoding="utf-8")
        (profile / "alltron-ha.service").write_text("[Unit]\nDescription=Expected HA\n", encoding="utf-8")
        (profile / "alltron.service").chmod(0o600)
        (profile / "alltron-ha.service").chmod(0o600)
        home = self.temp / "fictional-home"
        unit_dir = home / ".config" / "systemd" / "user"
        unit_dir.mkdir(parents=True)
        unit_dir.chmod(0o700)
        unknown = unit_dir / "alltron.service"
        unknown.write_text("[Unit]\nDescription=Third-party user service\n", encoding="utf-8")
        unknown.chmod(0o600)
        with (mock.patch.object(linux_install, "user"),
              mock.patch.object(linux_install, "safe_path", side_effect=lambda path: path),
              mock.patch.object(Path, "home", return_value=home),
              mock.patch.object(linux_install.shutil, "which", return_value="/fake/systemctl"),
              mock.patch.object(linux_install.subprocess, "run") as run):
            with self.assertRaisesRegex(ValueError, "service file preserved"):
                linux_install.service(profile, "uninstall-services")
        run.assert_not_called()
        self.assertEqual(unknown.read_text(encoding="utf-8"), "[Unit]\nDescription=Third-party user service\n")

    def test_two_unit_install_preflights_both_targets_before_writing(self):
        profile = self._profile()
        (profile / "services.json").write_text(json.dumps({"format": "alltron-services-1"}), encoding="utf-8")
        (profile / "services.json").chmod(0o600)
        expected_first = "[Unit]\nDescription=Alltron reviewed unit\n"
        (profile / "alltron.service").write_text(expected_first, encoding="utf-8")
        (profile / "alltron-ha.service").write_text("[Unit]\nDescription=Dedicated Alltron reviewed unit\n", encoding="utf-8")
        (profile / "alltron.service").chmod(0o600)
        (profile / "alltron-ha.service").chmod(0o600)
        home = self.temp / "fictional-two-unit-home"
        unit_dir = home / ".config" / "systemd" / "user"
        unit_dir.mkdir(parents=True)
        unit_dir.chmod(0o700)
        second = unit_dir / "alltron-ha.service"
        second.write_text("[Unit]\nDescription=Third-party HA service\n", encoding="utf-8")
        second.chmod(0o600)
        first = unit_dir / "alltron.service"

        with (mock.patch.object(linux_install, "user"),
              mock.patch.object(linux_install, "safe_path", side_effect=lambda path: path),
              mock.patch.object(Path, "home", return_value=home),
              mock.patch.object(linux_install.shutil, "which", return_value="/fake/systemctl"),
              mock.patch.object(linux_install.subprocess, "run") as run):
            with self.assertRaisesRegex(ValueError, "different service"):
                linux_install.service(profile, "install-services")
            self.assertFalse(first.exists())
            self.assertEqual(second.read_text(encoding="utf-8"), "[Unit]\nDescription=Third-party HA service\n")

            first.write_text(expected_first, encoding="utf-8")
            first.chmod(0o600)
            with self.assertRaisesRegex(ValueError, "different service"):
                linux_install.service(profile, "install-services")
            self.assertEqual(first.read_text(encoding="utf-8"), expected_first)
            self.assertEqual(second.read_text(encoding="utf-8"), "[Unit]\nDescription=Third-party HA service\n")
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
