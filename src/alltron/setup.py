"""Explicit local owner enrollment and TLS provisioning; never imports a login cache."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import getpass
import hashlib
import json
import os
import shutil
import secrets
import ssl
import stat
import subprocess
import tempfile
from pathlib import Path

from .owner import OwnerAuth, password_record
from .private_files import checked_path, read_private_text


def sync_directory(path: Path) -> None:
    if os.name == "posix":
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


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
        sync_directory(path.parent)
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


def certificate_info(root: Path) -> dict:
    auth = OwnerAuth(root / "owner.json")
    auth.context()
    cert = Path(auth.data["certificate"])
    fingerprint = hashlib.sha256(ssl.PEM_cert_to_DER_cert(read_private_text(cert, 16384))).hexdigest()
    if read_private_text(root / "owner.json", 16384) != auth.raw:
        raise ValueError("Owner profile changed; retry certificate information")
    return {"certificate": str(cert), "sha256": fingerprint}


@contextmanager
def profile_lock(root: Path):
    if os.name != "posix" or os.geteuid() == 0:
        raise ValueError("Profile changes require an ordinary Linux owner")
    if not root.is_absolute() or ".." in root.parts or root == Path.home() or root == Path(root.anchor):
        raise ValueError("Use a dedicated private owner profile")
    checked_path(root, directory=True)
    if root.stat().st_uid != os.geteuid() or root.stat().st_mode & 0o077:
        raise ValueError("Use an owner-only profile")
    import fcntl
    path = root / ".setup.lock"
    if path.exists() or path.is_symlink():
        read_private_text(path, 1024)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "r+b") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise ValueError("Unsafe setup lock")
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def rotate_certificate(root: Path, *, openssl: str) -> dict:
    with profile_lock(root):
        return _rotate_certificate(root, openssl=openssl)


def _rotate_certificate(root: Path, *, openssl: str) -> dict:
    """Publish a validated TLS pair by changing only the atomic owner marker."""
    if os.name != "posix" or os.geteuid() == 0:
        raise ValueError("Certificate rotation requires an ordinary Linux owner")
    if not root.is_absolute() or ".." in root.parts or root == Path.home() or root == Path(root.anchor):
        raise ValueError("Use the dedicated private owner profile")
    checked_path(root, directory=True)
    auth = OwnerAuth(root / "owner.json")
    # The old certificate may have expired; validate its files without requiring
    # a network handshake so renewal remains possible.
    auth.context()
    target = root / ("tls-" + secrets.token_hex(16))
    with tempfile.TemporaryDirectory(dir=root, prefix=".rotate-") as staging:
        pending = Path(staging) / "profile"
        pending.mkdir(mode=0o700)
        cert, key = certificate(pending, "alltron", openssl)
        private_write(pending / "owner.json", json.dumps({**auth.data, "certificate": str(cert), "private_key": str(key)}))
        OwnerAuth(pending / "owner.json").context()
        (pending / "owner.json").unlink()
        pending.rename(target)
        sync_directory(root)
        try:
            private_write(root / "owner.json", json.dumps({**auth.data, "certificate": str(target / cert.name),
                                                           "private_key": str(target / key.name)}))
        except BaseException:
            # Publication may have succeeded before an fsync/interruption failed.
            # Remove only when the unchanged old marker is positively verified.
            try:
                old_marker_active = read_private_text(root / "owner.json", 16384) == auth.raw
            except (OSError, ValueError):
                old_marker_active = False
            if old_marker_active:
                for name in (cert.name, key.name):
                    (target / name).unlink()
                target.rmdir()
            raise
    return {"status": "certificate-rotated", **certificate_info(root)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--reset-password", action="store_true")
    operation.add_argument("--rotate-certificate", action="store_true")
    operation.add_argument("--certificate-info", action="store_true")
    args = parser.parse_args()
    try:
        if args.certificate_info:
            print(json.dumps(certificate_info(args.profile), sort_keys=True))
            return
        if args.reset_password:
            with profile_lock(args.profile):
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
        if args.rotate_certificate:
            print(json.dumps(rotate_certificate(args.profile, openssl=openssl), sort_keys=True))
            print("Restart Alltron and verify the new certificate fingerprint before trusting it. Existing sessions are revoked.")
            return
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
