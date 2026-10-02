"""Probe basic runner containment in the pinned Home Assistant image.

This is fixture evidence for container settings only. It does not exercise or
accept any Codex runtime, model, credential, or Alltron service configuration.
"""

from __future__ import annotations

import argparse
import http.server
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import threading

from tools.linux_install import HA_IMAGE, local_podman

TEST_IMAGE = HA_IMAGE
CONTAINER_PREFIX = "alltron-boundary-"
PROBE_TIMEOUT = 45
EXPECTED_CHECKS = frozenset({
    "nonroot_uid", "root_filesystem_readonly", "readonly_write_denied",
    "windows_host_sentinel_hidden", "home_host_sentinel_hidden",
    "host_loopback_probe_blocked", "nonroute_ip_blocked",
})

PROBE = r'''
import json, os, pathlib, socket, sys
windows_sentinel, home_sentinel, host_port = sys.argv[1], sys.argv[2], int(sys.argv[3])
mounts = pathlib.Path('/proc/mounts').read_text().splitlines()
root_mounts = [line.split() for line in mounts if len(line.split()) > 3 and line.split()[1] == '/']
root_readonly = bool(root_mounts) and all('ro' in item[3].split(',') for item in root_mounts)
try:
    pathlib.Path('/usr/local/share/alltron-runner-boundary-probe').write_text('probe')
    readonly_write_denied = False
except OSError:
    readonly_write_denied = True
def probe(host, port, http=False):
    try:
        with socket.create_connection((host, port), timeout=0.6) as conn:
            if http:
                conn.sendall(b'GET /boundary-probe HTTP/1.0\r\nHost: localhost\r\n\r\n')
                conn.recv(128)
        return False
    except OSError:
        return True
checks = {
    'nonroot_uid': os.geteuid() == 65534,
    'root_filesystem_readonly': root_readonly,
    'readonly_write_denied': readonly_write_denied,
    'windows_host_sentinel_hidden': not pathlib.Path(windows_sentinel).exists(),
    'home_host_sentinel_hidden': not pathlib.Path(home_sentinel).exists(),
    'host_loopback_probe_blocked': probe('127.0.0.1', host_port, True),
    'nonroute_ip_blocked': probe('198.51.100.1', 9),
}
print(json.dumps(checks, sort_keys=True))
sys.exit(0 if all(checks.values()) else 1)
'''


class _ProbeHandler(http.server.BaseHTTPRequestHandler):
    requests = 0

    def do_GET(self):
        type(self).requests += 1
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *_args):
        pass


def command(podman: list[str], container: str, host_port: int, windows_sentinel: Path,
            home_sentinel: Path, cidfile: Path, label: str) -> list[str]:
    """Build the fixed, no-bind-mount probe command for unit validation."""
    if (not container.startswith(CONTAINER_PREFIX)
            or not container.removeprefix(CONTAINER_PREFIX).isalnum()
            or isinstance(host_port, bool) or not 1 <= host_port <= 65535
            or not re.fullmatch(r"[0-9a-f]{32}", label)):
        raise ValueError("Invalid boundary probe parameters")
    return [*podman, "run", "--rm", "--name", container, "--cidfile", str(cidfile),
            "--label=io.alltron.boundary=" + label, "--pull=never", "--network=none",
            "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
            "--memory=256m", "--cpus=1", "--pids-limit=32", "--user=65534:65534",
            "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=16m,mode=1777",
            "--env=HOME=/nonexistent", "--env=TMPDIR=/tmp",
            "--entrypoint", "/usr/local/bin/python3", TEST_IMAGE, "-c", PROBE,
            str(windows_sentinel), str(home_sentinel), str(host_port)]


def _image_ready(podman: list[str], environment: dict[str, str]) -> str | None:
    try:
        image = subprocess.run([*podman, "image", "exists", TEST_IMAGE], stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10,
                               env=environment)
        if image.returncode:
            return "The pinned probe image is not already available"
    except (OSError, subprocess.SubprocessError):
        return "The pinned probe image is unavailable"
    return None


def _parse_checks(output: str) -> dict[str, bool]:
    checks = json.loads(output)
    if (not isinstance(checks, dict) or set(checks) != EXPECTED_CHECKS
            or any(type(value) is not bool for value in checks.values())):
        raise ValueError("Boundary probe returned an unexpected check set")
    return checks


def _remove_container(podman: list[str], environment: dict[str, str], cidfile: Path, label: str) -> None:
    """Remove only a container whose private cidfile ID and probe label match."""
    try:
        if cidfile.is_symlink() or not cidfile.is_file() or cidfile.stat().st_size > 128:
            return
        identity = cidfile.read_text(encoding="ascii").strip()
        if not re.fullmatch(r"[0-9a-f]{64}", identity):
            return
        inspected = subprocess.run([*podman, "inspect", identity], stdin=subprocess.DEVNULL,
                                   capture_output=True, text=True, timeout=10, env=environment)
        if inspected.returncode or len(inspected.stdout) > 65536:
            return
        records = json.loads(inspected.stdout)
        if (not isinstance(records, list) or len(records) != 1 or not isinstance(records[0], dict)
                or records[0].get("Id") != identity
                or records[0].get("Config", {}).get("Labels", {}).get("io.alltron.boundary") != label):
            return
        subprocess.run([*podman, "rm", "--force", identity], stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10,
                       env=environment, check=True)
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, UnicodeError):
        pass


def rehearse() -> dict:
    if sys.platform != "linux" or os.geteuid() == 0:
        return {"status": "unavailable", "acceptance": False,
                "reason": "Run as an ordinary Linux user with rootless Podman"}
    try:
        podman, environment = local_podman()
    except (OSError, subprocess.SubprocessError, ValueError):
        return {"status": "unavailable", "acceptance": False,
                "reason": "Local rootless Podman is unavailable"}
    unavailable = _image_ready(podman, environment)
    if unavailable:
        return {"status": "unavailable", "acceptance": False, "reason": unavailable}

    name = CONTAINER_PREFIX + secrets.token_hex(12)
    label = secrets.token_hex(16)
    with tempfile.TemporaryDirectory(prefix="alltron-fictional-boundary-") as temporary:
        root = Path(temporary)
        os.chmod(root, 0o700)
        fake_windows = root / "windows-host-sentinel"
        fake_home = root / "home-host-sentinel"
        fake_windows.write_text(secrets.token_urlsafe(32), encoding="utf-8")
        fake_home.write_text(secrets.token_urlsafe(32), encoding="utf-8")
        cidfile = root / "container.cid"
        _ProbeHandler.requests = 0
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _ProbeHandler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            cmd = command(podman, name, server.server_port, fake_windows, fake_home, cidfile, label)
            try:
                result = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True,
                                        text=True, timeout=PROBE_TIMEOUT, env=environment)
            except (OSError, subprocess.SubprocessError) as exc:
                _remove_container(podman, environment, cidfile, label)
                return {"status": "failed", "acceptance": False,
                        "reason": f"Boundary probe did not complete ({type(exc).__name__})"}
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)

        try:
            checks = _parse_checks(result.stdout)
        except (ValueError, json.JSONDecodeError):
            _remove_container(podman, environment, cidfile, label)
            return {"status": "failed", "acceptance": False, "reason": "Boundary probe returned invalid results"}
        checks["host_received_no_requests"] = _ProbeHandler.requests == 0
        passed = result.returncode == 0 and bool(checks) and all(checks.values())
        if not passed:
            _remove_container(podman, environment, cidfile, label)
        return {"status": "passed" if passed else "failed", "acceptance": False,
                "scope": "container fixture boundary only", "checks": checks}


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    result = rehearse()
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
