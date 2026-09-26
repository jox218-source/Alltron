"""Rehearse an actual source archive using disposable files and loopback only."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

from .preview_install import InstallError, child_environment, initialize, install, status


def rehearse(archive: Path) -> None:
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="alltron-rehearsal-") as directory:
        root = Path(directory) / "preview"
        initialize(root)
        first = install(root, archive, digest)
        assert install(root, archive, digest) == first
        assert status(root)["current"]["archive_sha256"] == digest
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        program = ("import sys,pathlib;sys.path.insert(0,sys.argv[1]);"
                   "from tools.preview_install import serve_locked;serve_locked(pathlib.Path(sys.argv[2]),int(sys.argv[3]))")
        process = subprocess.Popen([sys.executable, "-I", "-B", "-c", program,
                                    str(Path(__file__).resolve().parents[1]), str(root), str(port)],
                                   cwd=root, env=child_environment(), stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            url = f"http://127.0.0.1:{port}"
            deadline = time.monotonic() + 10
            while True:
                if process.poll() is not None:
                    raise RuntimeError("Managed preview exited before becoming ready")
                try:
                    with opener.open(url + "/api/health", timeout=1) as response:
                        health = json.load(response)
                    break
                except (urllib.error.URLError, TimeoutError):
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Managed preview did not become ready") from None
                    time.sleep(0.05)
            assert health["home_assistant"] == "not-configured" and health["codex"] == "not-configured"
            request = urllib.request.Request(url + "/api/timers", data=json.dumps({"seconds": 120, "label": "Preview rehearsal"}).encode(),
                                             headers={"Content-Type": "application/json", "Origin": url})
            with opener.open(request, timeout=2) as response:
                assert response.status == 201
            try:
                install(root, archive, digest)
            except InstallError as error:
                assert "busy" in str(error)
            else:
                raise AssertionError("Running preview did not retain its update lock")
        finally:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        database = root / "data" / "timers.sqlite3"
        state_before = database.read_bytes()
        install(root, archive, digest)
        assert database.read_bytes() == state_before
    print("PASS: actual archive install, repeat install, local run, update lock and unchanged owner state")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    rehearse(args.archive)


if __name__ == "__main__":
    main()
