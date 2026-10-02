"""Synthetic owner-bound Home Assistant setup tests with fictional OAuth values."""

from __future__ import annotations

import json
import os
import ssl
import tempfile
import threading
import time
import unittest
from unittest import mock
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from alltron.ha_setup import HASetup
from alltron.private_files import read_private_text
from tls_fixtures import make_certificate

FAKE_ACCESS_TOKEN = "fictional-access-for-tests"
FAKE_REFRESH_TOKEN = "fictional-refresh-for-tests"


class FakeOAuthHA(BaseHTTPRequestHandler):
    calls = []
    token_number = 0

    def log_message(self, *_args):
        pass

    def _respond(self, body):
        encoded = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self):
        params = parse_qs(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode())
        type(self).calls.append((self.path, params, self.headers.get("Authorization")))
        if self.path == "/auth/token":
            type(self).token_number += 1
            self._respond({"token_type": "Bearer", "access_token": f"{FAKE_ACCESS_TOKEN}-{self.token_number}",
                           "refresh_token": FAKE_REFRESH_TOKEN, "expires_in": 3600})
        elif self.path == "/auth/revoke":
            self._respond({"revoked": True})
        else:
            self.send_error(404)

    def do_GET(self):
        type(self).calls.append((self.path, {}, self.headers.get("Authorization")))
        if self.path == "/api/states":
            self._respond([
                {"entity_id": "light.fictional_lamp", "attributes": {"friendly_name": "Fictional Lamp"}},
                {"entity_id": "switch.fictional_fan", "attributes": {"friendly_name": "Fictional Fan"}},
                {"entity_id": "lock.fictional_door", "attributes": {"friendly_name": "Fictional Lock"}},
                {"entity_id": "light.*", "attributes": {"friendly_name": "Invalid wildcard"}},
            ])
        else:
            self.send_error(404)


class HASetupTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.root.chmod(0o700)
        self.cert, self.key = make_certificate(self.root, "ha")
        FakeOAuthHA.calls = []
        FakeOAuthHA.token_number = 0
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOAuthHA)
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.minimum_version = ssl.TLSVersion.TLSv1_2
        tls.load_cert_chain(self.cert, self.key)
        self.server.socket = tls.wrap_socket(self.server.socket, server_side=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.setup = HASetup(self.root, self.server.server_port, self.cert)
        self.origin = f"https://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.directory.cleanup()

    def test_owner_session_binding_and_one_time_callback_state(self):
        result = self.setup.begin("fictional-owner-session-a", self.origin)
        query = parse_qs(urlsplit(result["url"]).query)
        state = query["state"][0]
        self.assertEqual(query["client_id"], [self.origin + "/"])
        self.assertEqual(query["redirect_uri"], [self.origin + "/auth/ha-callback"])
        with self.assertRaisesRegex(ValueError, "expired"):
            self.setup.exchange("fictional-owner-session-b", state, "fictional-code")
        with self.assertRaisesRegex(ValueError, "expired"):
            self.setup.exchange("fictional-owner-session-a", state, "fictional-code")
        self.assertEqual(FakeOAuthHA.calls, [])

    def test_callback_state_expires(self):
        result = self.setup.begin("fictional-owner-session", self.origin)
        state = parse_qs(urlsplit(result["url"]).query)["state"][0]
        self.setup.pending[state] = ("fictional-owner-session", self.origin + "/", time.monotonic() - 1)
        with self.assertRaisesRegex(ValueError, "expired"):
            self.setup.exchange("fictional-owner-session", state, "fictional-code")
        self.assertEqual(FakeOAuthHA.calls, [])

    def test_oauth_tokens_use_verified_tls_and_refresh_before_expiry(self):
        result = self.setup.begin("fictional-owner-session", self.origin)
        state = parse_qs(urlsplit(result["url"]).query)["state"][0]
        self.setup.exchange("fictional-owner-session", state, "fictional-code")
        self.assertEqual(self.setup.token(), f"{FAKE_ACCESS_TOKEN}-1")
        self.assertEqual(FakeOAuthHA.calls[0][0], "/auth/token")
        self.assertEqual(FakeOAuthHA.calls[0][1]["code"], ["fictional-code"])
        session_path = self.root / "ha-session.json"
        session = json.loads(read_private_text(session_path, 16384))
        session["expires"] = time.time() + 1
        session_path.write_text(json.dumps(session), encoding="utf-8")
        session_path.chmod(0o600)
        self.assertEqual(self.setup.token(), f"{FAKE_ACCESS_TOKEN}-2")
        refresh_call = FakeOAuthHA.calls[-1]
        self.assertEqual(refresh_call[1]["grant_type"], ["refresh_token"])
        self.assertEqual(refresh_call[1]["refresh_token"], [FAKE_REFRESH_TOKEN])

    def test_certificate_failure_has_no_http_fallback(self):
        wrong_cert, _ = make_certificate(self.root, "untrusted")
        untrusted_setup = HASetup(self.root, self.server.server_port, wrong_cert)
        before = len(FakeOAuthHA.calls)
        with self.assertRaises((OSError, ssl.SSLError)):
            untrusted_setup.begin("fictional-owner-session", self.origin)
        self.assertEqual(len(FakeOAuthHA.calls), before)
        self.assertTrue(all(not call[0].startswith("http://") for call in FakeOAuthHA.calls))

    def test_device_selection_allows_only_listed_light_and_switch(self):
        result = self.setup.begin("fictional-owner-session", self.origin)
        state = parse_qs(urlsplit(result["url"]).query)["state"][0]
        self.setup.exchange("fictional-owner-session", state, "fictional-code")
        adapter = self.setup.select({"Fictional Lamp": "light.fictional_lamp"})
        self.assertEqual(adapter.aliases, {"fictional lamp": "light.fictional_lamp"})
        self.assertEqual(FakeOAuthHA.calls[-1][0], "/api/states")
        self.assertEqual(FakeOAuthHA.calls[-1][2], f"Bearer {FAKE_ACCESS_TOKEN}-1")
        with self.assertRaisesRegex(ValueError, "listed"):
            self.setup.select({"Door": "lock.fictional_door"})

    def test_revoke_calls_service_and_removes_local_authorization_files(self):
        result = self.setup.begin("fictional-owner-session", self.origin)
        state = parse_qs(urlsplit(result["url"]).query)["state"][0]
        self.setup.exchange("fictional-owner-session", state, "fictional-code")
        self.setup.select({"Lamp": "light.fictional_lamp"})
        self.assertEqual(self.setup.revoke()["home_assistant"], "needs-authorization")
        revoke = next(call for call in FakeOAuthHA.calls if call[0] == "/auth/revoke")
        self.assertEqual(revoke[1]["token"], [FAKE_REFRESH_TOKEN])
        for name in ("ha.json", "ha-session.json", "ha-access.token"):
            self.assertFalse((self.root / name).exists())
        self.assertEqual(self.setup.pending, {})

    def _write_local_auth_files(self, *, session=None):
        contents = {
            "ha.json": json.dumps({"fixture": "selected fictional device"}),
            "ha-session.json": json.dumps(session if session is not None else {
                "client": self.origin + "/", "refresh": FAKE_REFRESH_TOKEN,
                "expires": time.time() + 3600,
            }),
            "ha-access.token": FAKE_ACCESS_TOKEN,
        }
        for name, value in contents.items():
            path = self.root / name
            path.write_text(value, encoding="utf-8")
            path.chmod(0o600)

    def test_disconnect_is_offline_for_malformed_expired_and_unavailable_grants(self):
        cases = {
            "malformed": "not-json",
            "expired": json.dumps({"client": self.origin + "/", "refresh": FAKE_REFRESH_TOKEN,
                                   "expires": time.time() - 10}),
            "offline": json.dumps({"client": self.origin + "/", "refresh": FAKE_REFRESH_TOKEN,
                                   "expires": time.time() + 3600}),
        }
        with mock.patch.object(self.setup, "_request", side_effect=AssertionError("disconnect must stay offline")) as request:
            for case, grant in cases.items():
                with self.subTest(case=case):
                    self._write_local_auth_files()
                    (self.root / "ha-session.json").write_text(grant, encoding="utf-8")
                    (self.root / "ha-session.json").chmod(0o600)
                    self.setup.pending["fixture-state"] = ("fixture-owner", self.origin + "/", time.monotonic() + 20)
                    self.assertEqual(self.setup.disconnect()["home_assistant"], "needs-authorization")
                    self.assertEqual(self.setup.pending, {})
                    self.assertTrue(all(not (self.root / name).exists()
                                        for name in ("ha.json", "ha-session.json", "ha-access.token")))
        request.assert_not_called()
        self.assertEqual(FakeOAuthHA.calls, [])

    def test_remote_revoke_failure_retains_local_state_until_explicit_disconnect(self):
        self._write_local_auth_files()
        self.setup.pending["fixture-state"] = ("fixture-owner", self.origin + "/", time.monotonic() + 20)
        paths = [self.root / name for name in ("ha.json", "ha-session.json", "ha-access.token")]
        with mock.patch.object(self.setup, "_request", side_effect=OSError("fictional HA offline")) as request:
            with self.assertRaises(OSError):
                self.setup.revoke()
        request.assert_called_once()
        self.assertTrue(all(path.is_file() for path in paths))
        self.assertIn("fixture-state", self.setup.pending)
        with mock.patch.object(self.setup, "_request") as request:
            result = self.setup.disconnect()
        request.assert_not_called()
        self.assertEqual(result["home_assistant"], "needs-authorization")
        self.assertEqual(self.setup.pending, {})
        self.assertTrue(all(not path.exists() for path in paths))

    def test_expired_session_revoke_sends_revoke_without_refresh(self):
        expired = {"client": self.origin + "/", "refresh": FAKE_REFRESH_TOKEN,
                   "expires": time.time() - 3600}
        self._write_local_auth_files(session=expired)
        result = self.setup.revoke()
        self.assertEqual(result["remote_revocation"], "requested-not-confirmed")
        self.assertEqual([call[0] for call in FakeOAuthHA.calls], ["/auth/revoke"])
        self.assertEqual(FakeOAuthHA.calls[0][1]["token"], [FAKE_REFRESH_TOKEN])

    def test_malformed_token_type_leaves_no_authorization_files(self):
        for token_type in (None, False, 7, [], {}):
            with self.subTest(token_type=token_type), self.assertRaises(ValueError):
                self.setup._save_session({"token_type": token_type}, self.origin + "/")
        self.assertFalse((self.root / "ha-access.token").exists())
        self.assertFalse((self.root / "ha-session.json").exists())


if __name__ == "__main__":
    unittest.main()
