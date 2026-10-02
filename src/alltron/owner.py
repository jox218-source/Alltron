"""Local owner login. Credentials belong to a separate private installation profile."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import ssl
import tempfile
import threading
import time
from http.cookies import SimpleCookie, CookieError
from pathlib import Path

from .private_files import read_private_text

ITERATIONS = 600000
SESSION_SECONDS = 8 * 60 * 60
MAX_SESSIONS = 8
COOKIE = "__Host-alltron"
HEX = re.compile(r"[0-9a-f]{64}\Z")


def password_record(password: str) -> dict:
    if not isinstance(password, str) or not 12 <= len(password) <= 256:
        raise ValueError("Choose an owner password containing 12 to 256 characters")
    salt = secrets.token_hex(32)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), ITERATIONS)
    return {"salt": salt, "password_hash": digest.hex()}


class LoginLimited(ValueError):
    pass


class OwnerAuth:
    def __init__(self, profile: Path):
        self.profile = profile
        self.raw = read_private_text(profile, 16384)
        data = json.loads(self.raw)
        if (not isinstance(data, dict) or set(data) != {"format", "salt", "password_hash", "certificate", "private_key"}
                or data["format"] != "alltron-owner-1"
                or not isinstance(data["salt"], str) or not HEX.fullmatch(data["salt"])
                or not isinstance(data["password_hash"], str) or not HEX.fullmatch(data["password_hash"])
                or not isinstance(data["certificate"], str) or not isinstance(data["private_key"], str)):
            raise ValueError("Owner profile is invalid; rerun local setup")
        self.data = data
        self.sessions: dict[str, tuple[float, str]] = {}
        self.attempts: list[float] = []
        self.lock = threading.Lock()

    def context(self) -> ssl.SSLContext:
        # Load from verified bounded contents in a private temporary directory,
        # rather than letting the SSL library reopen unverified source paths.
        certificate = read_private_text(Path(self.data["certificate"]), 16384)
        key = read_private_text(Path(self.data["private_key"]), 16384)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        with tempfile.TemporaryDirectory(prefix="alltron-tls-") as temporary:
            root = Path(temporary)
            root.chmod(0o700)
            cert_file, key_file = root / "certificate", root / "key"
            cert_file.write_text(certificate, encoding="utf-8")
            key_file.write_text(key, encoding="utf-8")
            cert_file.chmod(0o600)
            key_file.chmod(0o600)
            context.load_cert_chain(cert_file, key_file)
        return context

    def _unchanged(self) -> bool:
        try:
            unchanged = hmac.compare_digest(read_private_text(self.profile, 16384).encode(), self.raw.encode())
        except (OSError, ValueError):
            unchanged = False
        if not unchanged:
            self.sessions.clear()
        return unchanged

    @staticmethod
    def cookie_identity(header: str | None) -> str | None:
        if not header or len(header) > 4096:
            return None
        try:
            cookie = SimpleCookie(header)
            value = cookie[COOKIE].value if COOKIE in cookie else ""
        except CookieError:
            return None
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", value):
            return None
        return hashlib.sha256(value.encode("ascii")).hexdigest()

    def authorized(self, header: str | None) -> bool:
        with self.lock:
            if not self._unchanged():
                return False
            now = time.monotonic()
            self.sessions = {identity: value for identity, value in self.sessions.items() if value[0] > now}
            return self.cookie_identity(header) in self.sessions

    def csrf(self, header: str | None) -> str | None:
        if not self.authorized(header):
            return None
        with self.lock:
            value = self.sessions.get(self.cookie_identity(header))
            return value[1] if value else None

    def login(self, password: str, previous: str | None = None) -> str | None:
        if not isinstance(password, str) or not 1 <= len(password) <= 256:
            return None
        with self.lock:
            now = time.monotonic()
            self.attempts = [stamp for stamp in self.attempts if now - stamp < 60]
            if len(self.attempts) >= 5:
                raise LoginLimited("Too many unlock attempts; wait one minute")
            self.attempts.append(now)
            if not self._unchanged():
                return None
            digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                         bytes.fromhex(self.data["salt"]), ITERATIONS).hex()
            if not hmac.compare_digest(digest, self.data["password_hash"]):
                return None
            self.sessions.pop(self.cookie_identity(previous), None)
            self.sessions = {identity: value for identity, value in self.sessions.items() if value[0] > now}
            if len(self.sessions) >= MAX_SESSIONS:
                self.sessions.pop(next(iter(self.sessions)))
            token = secrets.token_urlsafe(32)
            self.sessions[hashlib.sha256(token.encode()).hexdigest()] = (now + SESSION_SECONDS, secrets.token_hex(32))
            return f"{COOKIE}={token}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age={SESSION_SECONDS}"

    def logout(self, header: str | None) -> str:
        with self.lock:
            self.sessions.pop(self.cookie_identity(header), None)
        return f"{COOKIE}=; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=0"
