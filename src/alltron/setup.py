"""Explicit local owner enrollment and TLS provisioning; never imports a login cache."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .owner import OwnerAuth, password_record
from .private_files import checked_path, read_private_text


def private_write(path: Path, data: str) -> None:
    checked_path(path.parent, directory=True)
    if os.name == "posix" and (path.parent.stat().st_uid != os.geteuid() or path.parent.stat().st_mode & 0o077):
        raise ValueError("Setup requires an owner-only parent directory")
    if path.exists() or path.is_symlink():
        read_private_text(path, 256 * 1024)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".write-")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if Path(temporary).exists():
            Path(temporary).unlink()


def certificate(root: Path, name: str, openssl: str) -> tuple[Path, Path]:
    if name not in {"alltron", "ha"} or not Path(openssl).is_absolute():
        raise ValueError("Use the reviewed TLS generation command")
    cert, key = root / (name + ".crt"), root / (name + ".key")
    if cert.exists() or key.exists():
        raise ValueError("Certificate files already exist; keep or explicitly rotate the profile")
    with tempfile.TemporaryDirectory(dir=root, prefix=".certificate-") as temporary:
        temporary_root = Path(temporary)
        result = subprocess.run([openssl, "req", "-x509", "-newkey", "rsa:3072", "-sha256", "-days", "365",
                                 "-nodes", "-keyout", "key", "-out", "certificate", "-subj", "/CN=alltron-local",
                                 "-addext", "subjectAltName=IP:127.0.0.1"],
                                cwd=temporary_root, env={"PATH": os.defpath}, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        if result.returncode:
            raise ValueError("TLS generation failed; check the local OpenSSL installation")
        (temporary_root / "key").chmod(0o600)
        (temporary_root / "certificate").chmod(0o600)
        private_write(cert, read_private_text(temporary_root / "certificate", 16384))
        private_write(key, read_private_text(temporary_root / "key", 16384))
    return cert, key


def enroll(root: Path, password: str, *, openssl: str) -> dict:
    if os.name != "posix" or os.geteuid() == 0:
        raise ValueError("Owner setup supports an ordinary Linux user; do not use sudo")
    if not root.is_absolute() or ".." in root.parts or root == Path.home() or root == Path(root.anchor):
        raise ValueError("Choose an absolute dedicated profile outside repositories")
    checked_path(root.parent, directory=True)
    record = password_record(password)
    if root.exists():
        checked_path(root, directory=True)
        if root.stat().st_uid != os.geteuid() or root.stat().st_mode & 0o077:
            raise ValueError("Existing profile must be private and owned by this user")
        if (root / "owner.json").exists():
            OwnerAuth(root / "owner.json").context()
            return {"status": "already-enrolled"}
        if any(root.iterdir()):
            raise ValueError("Choose an empty profile; incomplete setup is never overwritten")
    with tempfile.TemporaryDirectory(dir=root.parent, prefix=".alltron-enroll-") as staging:
        pending = Path(staging) / "profile"
        pending.mkdir(mode=0o700)
        cert, key = certificate(pending, "alltron", openssl)
        data = {"format": "alltron-owner-1", **record, "certificate": str(cert), "private_key": str(key)}
        private_write(pending / "owner.json", json.dumps(data))
        OwnerAuth(pending / "owner.json").context()
        private_write(pending / "owner.json", json.dumps({**data, "certificate": str(root / cert.name),
                                                         "private_key": str(root / key.name)}))
        if root.exists():
            root.rmdir()  # Only the validated empty directory may be replaced.
        pending.rename(root)
    return {"status": "enrolled"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--reset-password", action="store_true")
    args = parser.parse_args()
    try:
        if args.reset_password:
            auth = OwnerAuth(args.profile / "owner.json")
            password = getpass.getpass("New local Alltron password (12+ characters): ")
            if password != getpass.getpass("Repeat password: "):
                raise ValueError("Passwords did not match")
            private_write(args.profile / "owner.json", json.dumps({**auth.data, **password_record(password)}))
            print("Password changed; existing sessions are revoked. Restart Alltron.")
            return
        openssl = shutil.which("openssl")
        if not openssl:
            raise ValueError("Install OpenSSL before local owner setup")
        if (args.profile / "owner.json").exists():
            OwnerAuth(args.profile / "owner.json").context()
            print("Owner setup already exists; password and certificates preserved.")
            return
        password = getpass.getpass("Choose a local Alltron password (12+ characters): ")
        if password != getpass.getpass("Repeat password: "):
            raise ValueError("Passwords did not match")
        result = enroll(args.profile, password, openssl=openssl)
        print(result["status"] + ". Verify/trust only this profile's TLS certificate before browser login.")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        parser.exit(1, "Owner setup stopped. Check the private profile, password and Linux/OpenSSL prerequisites.\n")


if __name__ == "__main__":
    main()
