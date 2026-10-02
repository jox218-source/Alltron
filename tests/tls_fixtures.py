"""Generated TLS fixtures for synthetic local integration tests."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def _openssl() -> str | None:
    found = shutil.which("openssl")
    if found:
        return found
    if os.name == "nt":
        candidates = (Path("C:/Program Files/Git/usr/bin/openssl.exe"),
                      Path("C:/Program Files/Git/mingw64/bin/openssl.exe"))
        return next((str(candidate) for candidate in candidates if candidate.is_file()), None)
    return None


def make_certificate(root: Path, name: str = "fixture", san: str = "IP:127.0.0.1") -> tuple[Path, Path]:
    """Generate a short lived self-signed RSA certificate and key under root."""
    openssl = _openssl()
    if openssl is None:
        raise FileNotFoundError("OpenSSL is required to generate TLS test fixtures")
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o700)
    cert = root / f"{name}.crt"
    key = root / f"{name}.key"
    subprocess.run([openssl, "req", "-x509", "-newkey", "rsa:2048", "-sha256", "-days", "1",
                    "-nodes", "-keyout", str(key), "-out", str(cert), "-subj", "/CN=fixture.invalid",
                    "-addext", f"subjectAltName={san}"], check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)
    key.chmod(0o600)
    cert.chmod(0o600)
    return cert, key
