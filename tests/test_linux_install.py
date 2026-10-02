"""Fictional Linux setup tests; no host services, containers, or appliances are started."""

from __future__ import annotations

import json
import os
import secrets
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
        self.profile_password = secrets.token_urlsafe(24)
        profile.joinpath("owner.json").write_text(json.dumps({
            "format": "alltron-owner-1", **password_record(self.profile_password),
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

    def _ha_marker(self):
        root = self.temp / "fictional-ha-lifecycle"
        root.mkdir(mode=0o700)
        root.chmod(0o700)
        identity = "a1b2c3d4" * 4
        marker = root / "alltron-ha.json"
        marker.write_text(json.dumps({"format": "alltron-ha-1", "image": linux_install.HA_IMAGE,
                                      "port": 8123, "identity": identity}), encoding="utf-8")
        marker.chmod(0o600)
        return root, identity

    def _inspect_result(self, root, identity, *, running=False, image=None, label=None, source=None,
                        immutable_id="0123456789abcdef" * 4):
        metadata = {"Config": {"Labels": {"io.alltron.identity": label if label is not None else identity},
                                "Image": image if image is not None else linux_install.HA_IMAGE},
                    "Mounts": [{"Source": str(root) if source is None else source, "Destination": "/config"}],
                    "State": {"Running": running, "Status": "running" if running else "exited"}, "Id": immutable_id}
        return mock.Mock(returncode=0, stdout=json.dumps([metadata]))

    @staticmethod
    def _mock_lifecycle(outcomes):
        calls = []

        def invoke(args, **kwargs):
            calls.append(list(args))
            result = outcomes[len(calls) - 1]
            if isinstance(result, BaseException):
                raise result
            return result

        return calls, invoke

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
        owner_setup.rotate_certificate(profile, openssl=OPENSSL)
        active_certificate_info = owner_setup.certificate_info(profile)
        manifest = {"version": "0.1.0-fictional"}
        real_run = linux_install.subprocess.run
        with (mock.patch.object(linux_install, "safe_path", side_effect=lambda path: path),
              mock.patch.object(linux_install, "local_podman", return_value=(["/fake/podman", "--remote=false"], {})),
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
        self.assertIn("run-ha --ha-root", ha_unit)
        self.assertIn("stop-ha --ha-root", ha_unit)
        self.assertNotIn("podman run", ha_unit)
        marker = json.loads((ha_root / "alltron-ha.json").read_text(encoding="utf-8"))
        self.assertEqual(marker["image"], linux_install.HA_IMAGE)
        self.assertRegex(marker["identity"], r"\A[0-9a-f]{32}\Z")
        self.assertTrue((profile / "owner.json").is_file())
        self.assertTrue((ha_root / "ha.crt").is_file())
        self.assertTrue((ha_root / "ha.key").is_file())
        self.assertTrue((ha_root / "ha.key").read_text(encoding="utf-8").startswith("-----BEGIN "))
        self.assertEqual(result["certificate_sha256"]["alltron.crt"], active_certificate_info["sha256"])

    @unittest.skipUnless(OPENSSL and sys.platform == "linux" and os.name == "posix",
                         "Linux owner enrollment requires OpenSSL")
    def test_enrollment_creates_valid_tls_profile_and_repeat_preserves_it(self):
        if os.geteuid() == 0:
            self.skipTest("Owner enrollment intentionally refuses root")
        profile = self.temp / "enrolled-profile"
        password = secrets.token_urlsafe(24)
        result = owner_setup.enroll(profile, password, openssl=OPENSSL)
        self.assertEqual(result["status"], "enrolled")
        auth = OwnerAuth(profile / "owner.json")
        context = auth.context()
        self.assertEqual(context.minimum_version.name, "TLSv1_2")
        cert_before = (profile / "alltron.crt").read_bytes()
        key_before = (profile / "alltron.key").read_bytes()
        self.assertEqual(owner_setup.enroll(profile, secrets.token_urlsafe(24), openssl=OPENSSL)["status"],
                         "already-enrolled")
        self.assertEqual((profile / "alltron.crt").read_bytes(), cert_before)
        self.assertEqual((profile / "alltron.key").read_bytes(), key_before)

    @unittest.skipUnless(sys.platform == "linux" and os.name == "posix", "Linux enrollment boundary")
    def test_openssl_failure_leaves_no_published_profile(self):
        if os.geteuid() == 0:
            self.skipTest("Owner enrollment intentionally refuses root")
        profile = self.temp / "failed-enrollment"
        with mock.patch.object(owner_setup.subprocess, "run", return_value=mock.Mock(returncode=1)):
            with self.assertRaisesRegex(ValueError, "TLS generation failed"):
                owner_setup.enroll(profile, secrets.token_urlsafe(24), openssl=OPENSSL or "/fake/openssl")
        self.assertFalse(profile.exists())
        self.assertFalse(list(self.temp.glob(".alltron-enroll-*")))

    def _enrolled_rotation_profile(self):
        profile = self.temp / "fictional-rotation-profile"
        password = secrets.token_urlsafe(24)
        owner_setup.enroll(profile, password, openssl=OPENSSL)
        return profile, password

    @unittest.skipUnless(OPENSSL and sys.platform == "linux" and os.name == "posix",
                         "Linux certificate rotation requires OpenSSL")
    def test_rotation_changes_fingerprint_preserves_password_and_revokes_old_session(self):
        if os.geteuid() == 0:
            self.skipTest("Certificate rotation requires an ordinary Linux user")
        profile, password = self._enrolled_rotation_profile()
        old_auth = OwnerAuth(profile / "owner.json")
        old_hash = old_auth.data["password_hash"]
        old_certificate = Path(old_auth.data["certificate"])
        old_key = Path(old_auth.data["private_key"])
        old_cert_bytes, old_key_bytes = old_certificate.read_bytes(), old_key.read_bytes()
        old_info = owner_setup.certificate_info(profile)
        cookie = old_auth.login(password).split(";", 1)[0]
        self.assertTrue(old_auth.authorized(cookie))

        result = owner_setup.rotate_certificate(profile, openssl=OPENSSL)

        new_auth = OwnerAuth(profile / "owner.json")
        new_info = owner_setup.certificate_info(profile)
        new_auth.context()
        self.assertEqual(result["status"], "certificate-rotated")
        self.assertNotEqual(new_info["sha256"], old_info["sha256"])
        self.assertEqual(new_auth.data["password_hash"], old_hash)
        self.assertEqual(old_certificate.read_bytes(), old_cert_bytes)
        self.assertEqual(old_key.read_bytes(), old_key_bytes)
        self.assertFalse(old_auth.authorized(cookie))

    @unittest.skipUnless(OPENSSL and sys.platform == "linux" and os.name == "posix",
                         "Linux certificate rotation requires OpenSSL")
    def test_rotation_generation_failure_preserves_marker_and_old_tls_pair(self):
        if os.geteuid() == 0:
            self.skipTest("Certificate rotation requires an ordinary Linux user")
        profile, _ = self._enrolled_rotation_profile()
        marker = (profile / "owner.json").read_bytes()
        auth = OwnerAuth(profile / "owner.json")
        cert = Path(auth.data["certificate"])
        key = Path(auth.data["private_key"])
        old_pair = cert.read_bytes(), key.read_bytes()
        with mock.patch.object(owner_setup.subprocess, "run", return_value=mock.Mock(returncode=1)):
            with self.assertRaisesRegex(ValueError, "TLS generation failed"):
                owner_setup.rotate_certificate(profile, openssl=OPENSSL)
        self.assertEqual((profile / "owner.json").read_bytes(), marker)
        self.assertEqual((cert.read_bytes(), key.read_bytes()), old_pair)
        self.assertFalse(list(profile.glob("tls-*")))
        self.assertFalse(list(profile.glob(".rotate-*")))

    @unittest.skipUnless(OPENSSL and sys.platform == "linux" and os.name == "posix",
                         "Linux certificate rotation requires OpenSSL")
    def test_marker_write_failure_removes_only_new_pair_and_preserves_old_profile(self):
        if os.geteuid() == 0:
            self.skipTest("Certificate rotation requires an ordinary Linux user")
        profile, _ = self._enrolled_rotation_profile()
        marker = (profile / "owner.json").read_bytes()
        auth = OwnerAuth(profile / "owner.json")
        cert = Path(auth.data["certificate"])
        key = Path(auth.data["private_key"])
        old_pair = cert.read_bytes(), key.read_bytes()
        real_write = owner_setup.private_write

        def fail_marker_write(path, data):
            if Path(path) == profile / "owner.json":
                raise OSError("fictional marker publication failure")
            return real_write(path, data)

        with mock.patch.object(owner_setup, "private_write", side_effect=fail_marker_write):
            with self.assertRaisesRegex(OSError, "publication failure"):
                owner_setup.rotate_certificate(profile, openssl=OPENSSL)
        self.assertEqual((profile / "owner.json").read_bytes(), marker)
        self.assertEqual((cert.read_bytes(), key.read_bytes()), old_pair)
        self.assertFalse(list(profile.glob("tls-*")))
        self.assertFalse(list(profile.glob(".rotate-*")))

    @unittest.skipUnless(OPENSSL and sys.platform == "linux" and os.name == "posix",
                         "Linux certificate rotation requires OpenSSL")
    def test_post_replace_fault_keeps_marker_targeted_valid_pair(self):
        if os.geteuid() == 0:
            self.skipTest("Certificate rotation requires an ordinary Linux owner")
        profile, _ = self._enrolled_rotation_profile()
        old_auth = OwnerAuth(profile / "owner.json")
        old_marker = old_auth.raw
        old_certificate = Path(old_auth.data["certificate"])
        old_key = Path(old_auth.data["private_key"])
        old_pair = old_certificate.read_bytes(), old_key.read_bytes()
        real_write = owner_setup.private_write

        def write_then_fail_marker(path, data):
            result = real_write(path, data)
            if Path(path) == profile / "owner.json":
                raise OSError("fictional post-replace sync failure")
            return result

        with mock.patch.object(owner_setup, "private_write", side_effect=write_then_fail_marker):
            with self.assertRaisesRegex(OSError, "post-replace"):
                owner_setup.rotate_certificate(profile, openssl=OPENSSL)

        current = OwnerAuth(profile / "owner.json")
        current.context()
        new_certificate = Path(current.data["certificate"])
        new_key = Path(current.data["private_key"])
        self.assertNotEqual(current.raw, old_marker)
        self.assertTrue(new_certificate.is_file())
        self.assertTrue(new_key.is_file())
        self.assertNotEqual(new_certificate, old_certificate)
        self.assertNotEqual(new_certificate.read_bytes(), old_pair[0])
        self.assertEqual(old_certificate.read_bytes(), old_pair[0])
        self.assertEqual(old_key.read_bytes(), old_pair[1])
        self.assertTrue(new_certificate.parent.is_dir())

    @unittest.skipUnless(OPENSSL and sys.platform == "linux" and os.name == "posix",
                         "Linux preparation lock requires OpenSSL")
    def test_contended_profile_lock_stops_prepare_before_writes(self):
        if os.geteuid() == 0:
            self.skipTest("Profile lock requires an ordinary Linux owner")
        root, profile, ha_root, _content = self._prepared_environment()
        with owner_setup.profile_lock(profile):
            marker = (profile / "owner.json").read_bytes()
            entries = {item.name for item in profile.iterdir()}
            with mock.patch.object(linux_install, "_prepare") as prepare:
                with self.assertRaises(OSError):
                    linux_install.prepare(root, profile, ha_root)
            prepare.assert_not_called()
            self.assertEqual((profile / "owner.json").read_bytes(), marker)
            self.assertEqual({item.name for item in profile.iterdir()}, entries)
            self.assertFalse(ha_root.exists())

    @unittest.skipUnless(OPENSSL and sys.platform == "linux" and os.name == "posix",
                         "Linux profile lock requires OpenSSL")
    def test_concurrent_profile_lock_refuses_rotation_without_changes(self):
        if os.geteuid() == 0:
            self.skipTest("Profile lock requires an ordinary Linux user")
        profile, _ = self._enrolled_rotation_profile()
        marker = (profile / "owner.json").read_bytes()
        auth = OwnerAuth(profile / "owner.json")
        cert = Path(auth.data["certificate"])
        key = Path(auth.data["private_key"])
        old_pair = cert.read_bytes(), key.read_bytes()
        with owner_setup.profile_lock(profile):
            with mock.patch.object(owner_setup.subprocess, "run") as run:
                with self.assertRaises(OSError):
                    owner_setup.rotate_certificate(profile, openssl=OPENSSL)
            run.assert_not_called()
        self.assertEqual((profile / "owner.json").read_bytes(), marker)
        self.assertEqual((cert.read_bytes(), key.read_bytes()), old_pair)
        self.assertFalse(list(profile.glob("tls-*")))

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

    def test_lifecycle_refuses_unrelated_container_before_removal_or_stop(self):
        root, identity = self._ha_marker()
        calls, invoke = self._mock_lifecycle([
            mock.Mock(returncode=0), self._inspect_result(root, identity, label="different-fictional-id")])
        with (mock.patch.object(linux_install, "user"),
              mock.patch.object(linux_install, "safe_path", side_effect=lambda path: path),
              mock.patch.object(linux_install, "local_podman", return_value=(["/fake/podman", "--remote=false"], {})),
              mock.patch.object(linux_install.subprocess, "run", side_effect=invoke)):
            with self.assertRaisesRegex(ValueError, "different container"):
                linux_install.ha_lifecycle(root)
        self.assertEqual(len(calls), 2)
        self.assertEqual([call[2] for call in calls], ["container", "inspect"])

    def test_lifecycle_refuses_to_start_already_running_owned_container(self):
        root, identity = self._ha_marker()
        calls, invoke = self._mock_lifecycle([
            mock.Mock(returncode=0), self._inspect_result(root, identity, running=True)])
        with (mock.patch.object(linux_install, "user"),
              mock.patch.object(linux_install, "safe_path", side_effect=lambda path: path),
              mock.patch.object(linux_install, "local_podman", return_value=(["/fake/podman", "--remote=false"], {})),
              mock.patch.object(linux_install.subprocess, "run", side_effect=invoke)):
            with self.assertRaisesRegex(ValueError, "already running"):
                linux_install.ha_lifecycle(root)
        self.assertEqual(len(calls), 2)
        self.assertEqual([call[2] for call in calls], ["container", "inspect"])

    def test_lifecycle_cleans_stopped_owned_container_then_uses_fixed_run_resources(self):
        root, identity = self._ha_marker()
        calls, invoke = self._mock_lifecycle([
            mock.Mock(returncode=0), self._inspect_result(root, identity),
            mock.Mock(returncode=0), mock.Mock(returncode=0)])
        with (mock.patch.object(linux_install, "user"),
              mock.patch.object(linux_install, "safe_path", side_effect=lambda path: path),
              mock.patch.object(linux_install, "local_podman", return_value=(["/fake/podman", "--remote=false"], {})),
              mock.patch.object(linux_install.subprocess, "run", side_effect=invoke)):
            linux_install.ha_lifecycle(root)
        self.assertEqual([call[2] for call in calls], ["container", "inspect", "rm", "run"])
        self.assertEqual(calls[2][-1], "0123456789abcdef" * 4)
        self.assertEqual(calls[-1][3], "--rm")
        self.assertIn("--pull=never", calls[-1])
        self.assertIn("--label=io.alltron.identity=" + identity, calls[-1])
        self.assertIn("--cap-drop=ALL", calls[-1])
        self.assertIn("--security-opt=no-new-privileges", calls[-1])
        self.assertIn("--pids-limit=256", calls[-1])
        self.assertIn("--memory=2g", calls[-1])
        self.assertIn("--publish=127.0.0.1:8123:8123", calls[-1])
        self.assertIn("--volume=" + str(root) + ":/config:Z", calls[-1])
        self.assertIn(linux_install.HA_IMAGE, calls[-1])
        self.assertNotIn("--replace", calls[-1])
        self.assertEqual(calls[-1][2], "run")

    def test_lifecycle_preserves_unexpected_owned_container_state(self):
        root, identity = self._ha_marker()
        inspected = self._inspect_result(root, identity)
        records = json.loads(inspected.stdout)
        records[0]["State"]["Status"] = "paused"
        inspected.stdout = json.dumps(records)
        calls, invoke = self._mock_lifecycle([mock.Mock(returncode=0), inspected])
        with (mock.patch.object(linux_install, "user"),
              mock.patch.object(linux_install, "safe_path", side_effect=lambda path: path),
              mock.patch.object(linux_install, "local_podman", return_value=(["/fake/podman", "--remote=false"], {})),
              mock.patch.object(linux_install.subprocess, "run", side_effect=invoke)):
            with self.assertRaisesRegex(ValueError, "Unexpected"):
                linux_install.ha_lifecycle(root)
        self.assertEqual(len(calls), 2)

    def test_stop_targets_only_a_matching_owned_container(self):
        root, identity = self._ha_marker()
        calls, invoke = self._mock_lifecycle([
            mock.Mock(returncode=0), self._inspect_result(root, identity, label="unowned-fixture")])
        with (mock.patch.object(linux_install, "user"),
              mock.patch.object(linux_install, "safe_path", side_effect=lambda path: path),
              mock.patch.object(linux_install, "local_podman", return_value=(["/fake/podman", "--remote=false"], {})),
              mock.patch.object(linux_install.subprocess, "run", side_effect=invoke)):
            with self.assertRaisesRegex(ValueError, "different container"):
                linux_install.ha_lifecycle(root, stop=True)
        self.assertEqual(len(calls),  2)
        self.assertNotIn("stop", [call[2] for call in calls])

        calls, invoke = self._mock_lifecycle([
            mock.Mock(returncode=0), self._inspect_result(root, identity, running=True),
            mock.Mock(returncode=0)])
        with (mock.patch.object(linux_install, "user"),
              mock.patch.object(linux_install, "safe_path", side_effect=lambda path: path),
              mock.patch.object(linux_install, "local_podman", return_value=(["/fake/podman", "--remote=false"], {})),
              mock.patch.object(linux_install.subprocess, "run", side_effect=invoke)):
            linux_install.ha_lifecycle(root, stop=True)
        self.assertEqual([call[2] for call in calls], ["container", "inspect", "stop"])
        self.assertEqual(calls[-1][-1], "0123456789abcdef" * 4)
        self.assertEqual(calls[-1][3:5], ["--time=20", "0123456789abcdef" * 4])


if __name__ == "__main__":
    unittest.main()
