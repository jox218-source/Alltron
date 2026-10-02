"""Unit validation for the fictional container-boundary probe command."""

import json
import secrets
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools.linux_install import HA_IMAGE
from tools.rehearse_runner_boundary import (CONTAINER_PREFIX, EXPECTED_CHECKS, TEST_IMAGE,
                                           _parse_checks, _remove_container, command)


class RunnerBoundaryCommandTests(unittest.TestCase):
    def setUp(self):
        self.podman = ["/synthetic/bin/podman", "--remote=false"]
        self.cidfile = Path("/tmp/fictional/container.cid")
        self.label = "a1b2c3d4" * 4
        self.command = command(self.podman, CONTAINER_PREFIX + "a1b2c3", 8765,
                               Path("/tmp/fictional/windows-sentinel"),
                               Path("/tmp/fictional/home-sentinel"), self.cidfile, self.label)

    def test_uses_the_pinned_fixture_image_and_containment_flags(self):
        args = self.command
        self.assertEqual(TEST_IMAGE, HA_IMAGE)
        self.assertEqual(args[0:3], ["/synthetic/bin/podman", "--remote=false", "run"])
        self.assertIn("--cidfile", args)
        self.assertIn(str(self.cidfile), args)
        self.assertIn("--label=io.alltron.boundary=" + self.label, args)
        self.assertIn("--pull=never", args)
        self.assertIn("--network=none", args)
        self.assertIn("--read-only", args)
        self.assertIn("--cap-drop=ALL", args)
        self.assertIn("--security-opt=no-new-privileges", args)
        self.assertIn("--memory=256m", args)
        self.assertIn("--cpus=1", args)
        self.assertIn("--pids-limit=32", args)
        self.assertIn("--user=65534:65534", args)
        self.assertIn("/tmp:rw,noexec,nosuid,nodev,size=16m,mode=1777", args)
        self.assertIn("--env=HOME=/nonexistent", args)
        self.assertIn("--env=TMPDIR=/tmp", args)
        self.assertIn("/usr/local/bin/python3", args)
        self.assertIn(TEST_IMAGE, args)

    def test_adds_no_host_mount_home_socket_or_device(self):
        forbidden = {"-v", "--volume", "--mount", "--device", "--privileged"}
        self.assertFalse(forbidden.intersection(self.command))
        self.assertFalse(any("/run/podman" in arg or ".sock" in arg for arg in self.command))
        self.assertIn("--env=HOME=/nonexistent", self.command)

    def test_passes_only_synthetic_sentinels_and_loopback_probe_port(self):
        self.assertEqual(self.command[-3:], [str(Path("/tmp/fictional/windows-sentinel")),
                                              str(Path("/tmp/fictional/home-sentinel")), "8765"])

    def test_rejects_invalid_container_names_and_ports(self):
        for name, port, label in (("other-container", 8765, self.label),
                           (CONTAINER_PREFIX + "bad-name", 8765, self.label),
                           (CONTAINER_PREFIX + "aabb", 0, self.label),
                           (CONTAINER_PREFIX + "aabb", 65536, self.label),
                           (CONTAINER_PREFIX + "aabb", True, self.label),
                           (CONTAINER_PREFIX + "aabb", 8765, "not-an-identity")):
            with self.subTest(name=name, port=port), self.assertRaises(ValueError):
                command(self.podman, name, port, Path("/tmp/a"), Path("/tmp/b"),
                        Path("/tmp/fixture.cid"), label)

    def test_cleanup_refuses_uncertain_identity_or_label(self):
        identity = "0123456789abcdef" * 4
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            root.chmod(0o700)
            cidfile = root / "probe.cid"
            cidfile.write_text(identity, encoding="ascii")
            inspect = mock.Mock(returncode=0, stdout=json.dumps([{
                "Id": identity,
                "Config": {"Labels": {"io.alltron.boundary": "different-label"}},
            }]))
            with mock.patch("tools.rehearse_runner_boundary.subprocess.run", return_value=inspect) as run:
                _remove_container(self.podman, {}, cidfile, self.label)
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args[0][-2:], ["inspect", identity])

    def test_probe_result_requires_exact_expected_boolean_checks(self):
        all_true = {name: True for name in EXPECTED_CHECKS}
        self.assertEqual(_parse_checks(json.dumps(all_true)), all_true)
        for invalid in ({}, {**all_true, "extra": True},
                        {**all_true, "nonroot_uid": 1}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                _parse_checks(json.dumps(invalid))

    def test_cleanup_removes_only_inspected_immutable_id_with_matching_label(self):
        identity = secrets.token_hex(32)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            root.chmod(0o700)
            cidfile = root / "probe.cid"
            cidfile.write_text(identity, encoding="ascii")
            inspect = mock.Mock(returncode=0, stdout=json.dumps([{
                "Id": identity,
                "Config": {"Labels": {"io.alltron.boundary": self.label}},
            }]))
            with mock.patch("tools.rehearse_runner_boundary.subprocess.run",
                            side_effect=[inspect, mock.Mock(returncode=0)]) as run:
                _remove_container(self.podman, {}, cidfile, self.label)
            self.assertEqual(run.call_count, 2)
            self.assertEqual(run.call_args.args[0][-3:], ["rm", "--force", identity])


if __name__ == "__main__":
    unittest.main()
