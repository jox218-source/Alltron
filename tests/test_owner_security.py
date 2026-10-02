"""Synthetic TLS owner-session security tests; all credentials are fictional."""

from __future__ import annotations

import http.client
import json
import os
import secrets
import socket
import ssl
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPSHandler, HTTPCookieProcessor, Request, build_opener

from alltron.commands import CommandRouter
from alltron.ha_setup import HASetup
from alltron.owner import OwnerAuth, password_record
from alltron.server import PreviewHTTPServer, handler_for
from alltron.timers import TimerStore
from tls_fixtures import make_certificate


class OwnerSecurityTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        os.chmod(self.root, 0o700)
        self.cert, self.key = make_certificate(self.root, "server")
        self.profile = self.root / "owner.json"
        self.password = secrets.token_urlsafe(24)
        self.wrong_password = secrets.token_urlsafe(24)
        self._write_profile()
        self.auth = OwnerAuth(self.profile)
        self.store = TimerStore(self.root / "state.sqlite3")
        self.router = CommandRouter(self.store)
        self.ha_setup = HASetup(self.root, 8123, self.cert)
        self.server = PreviewHTTPServer(("127.0.0.1", 0),
                                        handler_for(self.store, router=self.router,
                                                    auth=self.auth, ha_setup=self.ha_setup))
        self.server.tls_context = self.auth.context()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"https://127.0.0.1:{self.server.server_port}"
        trust = ssl.create_default_context(cafile=str(self.cert))
        self.client = build_opener(HTTPSHandler(context=trust))

    def _write_profile(self):
        self.profile.write_text(json.dumps({"format": "alltron-owner-1", **password_record(self.password),
                                             "certificate": str(self.cert), "private_key": str(self.key)}), encoding="utf-8")
        self.profile.chmod(0o600)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.directory.cleanup()

    def request(self, path, payload=None, *, csrf=None, origin=None, cookie=None, opener=None):
        data = None if payload is None else json.dumps(payload).encode()
        headers = {"Host": f"127.0.0.1:{self.server.server_port}"}
        if data is not None:
            headers.update({"Content-Type": "application/json", "Origin": origin or self.base})
        if csrf is not None:
            headers["X-Alltron-CSRF"] = csrf
        if cookie:
            headers["Cookie"] = cookie
        request = Request(self.base + path, data=data, headers=headers)
        try:
            with (opener or self.client).open(request, timeout=4) as response:
                return response.status, response.headers, response.read()
        except HTTPError as exc:
            return exc.code, exc.headers, exc.read()

    def session(self, cookie=None):
        status, _, body = self.request("/api/session", cookie=cookie)
        self.assertEqual(status, 200)
        return json.loads(body)

    def login(self):
        status, headers, body = self.request("/api/login", {"password": self.password})
        self.assertEqual(status, 200, body)
        cookie = headers.get("Set-Cookie")
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Secure", cookie)
        self.assertIn("SameSite=Strict", cookie)
        csrf = self.session(cookie.split(";", 1)[0])["csrf"]
        self.assertTrue(csrf)
        return cookie.split(";", 1)[0], csrf

    def test_session_login_actions_require_csrf_and_logout_expires_session(self):
        self.assertEqual(self.session(), {"authenticated": False, "csrf": None})
        self.assertEqual(self.request("/api/timers")[0], 401)
        self.assertEqual(self.request("/api/timers", {"seconds": 60})[0], 401)
        status, _, body = self.request("/api/login", {"password": self.wrong_password})
        self.assertEqual(status, 401)
        self.assertEqual(self.request("/api/login", {"password": self.password}, origin="https://foreign.invalid")[0], 403)
        cookie, csrf = self.login()
        self.assertTrue(self.session(cookie)["authenticated"])
        self.assertEqual(self.request("/api/timers", {"seconds": 60}, cookie=cookie)[0], 403)
        status, _, body = self.request("/api/timers", {"seconds": 60}, csrf=csrf, cookie=cookie)
        self.assertEqual(status, 201, body)
        status, headers, _ = self.request("/api/logout", {}, csrf=csrf, cookie=cookie)
        self.assertEqual(status, 200)
        self.assertIn("Max-Age=0", headers.get("Set-Cookie", ""))
        self.assertEqual(self.request("/api/timers", cookie=cookie)[0], 401)

    def test_profile_mutation_invalidates_existing_session(self):
        cookie, csrf = self.login()
        self.profile.write_text(self.profile.read_text(encoding="utf-8") + " ", encoding="utf-8")
        self.profile.chmod(0o600)
        self.assertEqual(self.request("/api/timers", {"seconds": 30}, csrf=csrf, cookie=cookie)[0], 401)

    def test_session_expiry_and_login_rate_limit(self):
        cookie, _ = self.login()
        identity = self.auth.cookie_identity(cookie)
        self.auth.sessions[identity] = (time.monotonic() - 1, "expired-csrf")
        self.assertEqual(self.request("/api/timers", cookie=cookie)[0], 401)
        self.auth.attempts.clear()
        for _ in range(5):
            self.assertEqual(self.request("/api/login", {"password": self.wrong_password})[0], 401)
        self.assertEqual(self.request("/api/login", {"password": self.password})[0], 429)

    def test_plaintext_and_untrusted_server_certificate_are_rejected(self):
        with self.assertRaises((URLError, OSError, ssl.SSLError)):
            build_opener().open("http://127.0.0.1:%d/api/session" % self.server.server_port, timeout=2)
        untrusted = ssl.create_default_context()
        with self.assertRaises((URLError, ssl.SSLError)):
            build_opener(HTTPSHandler(context=untrusted)).open(self.base + "/api/session", timeout=3)

    def test_stalled_tls_handshake_is_bounded(self):
        sock = socket.create_connection(("127.0.0.1", self.server.server_port), timeout=2)
        started = time.monotonic()
        try:
            sock.settimeout(5)
            self.assertEqual(sock.recv(1), b"")
            self.assertLess(time.monotonic() - started, 4.5)
        finally:
            sock.close()

    def test_ha_disconnect_endpoint_requires_owner_and_csrf_then_clears_adapter(self):
        names = ("ha.json", "ha-session.json", "ha-access.token")
        for name in names:
            path = self.root / name
            path.write_text("fictional local HA state", encoding="utf-8")
            path.chmod(0o600)
        self.ha_setup.pending["fixture-state"] = ("fixture-owner", self.base + "/", time.monotonic() + 20)
        self.router.home_assistant = object()

        self.assertEqual(self.request("/api/setup/ha/disconnect", {})[0], 401)
        cookie, csrf = self.login()
        self.assertEqual(self.request("/api/setup/ha/disconnect", {}, cookie=cookie)[0], 403)
        self.assertTrue(all((self.root / name).exists() for name in names))
        self.assertEqual(self.request("/api/setup/ha/disconnect", {}, csrf=csrf, cookie=cookie,
                                      origin="https://foreign.invalid")[0], 403)
        status, _, body = self.request("/api/setup/ha/disconnect", {}, csrf=csrf, cookie=cookie)
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body)["home_assistant"], "needs-authorization")
        self.assertEqual(self.ha_setup.pending, {})
        self.assertTrue(all(not (self.root / name).exists() for name in names))
        self.assertIsNone(self.router.home_assistant)

    def test_ha_callback_returns_bad_request_when_setup_is_disabled(self):
        store = TimerStore(self.root / "disabled-state.sqlite3")
        server = PreviewHTTPServer(("127.0.0.1", 0), handler_for(store, auth=self.auth))
        server.tls_context = self.auth.context()
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f"https://127.0.0.1:{server.server_port}"
        request = Request(base + "/auth/ha-callback?state=fixture-state",
                          headers={"Host": f"127.0.0.1:{server.server_port}"})
        try:
            with self.assertRaises(HTTPError) as raised:
                self.client.open(request, timeout=4)
            self.assertEqual(raised.exception.code, 400)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
