"""Synthetic loopback tests for HTTP connection and framing limits."""

from __future__ import annotations

import http.client
import os
import socket
import tempfile
import threading
import time
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

from alltron import server as server_module
from alltron.server import PreviewHTTPServer, handler_for
from alltron.timers import TimerStore


class RecordingRouter:
    def __init__(self):
        self.home_assistant = None
        self.calls = []

    def execute(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return {"status": "ok"}


class PreviewHTTPBoundsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        if os.name == "posix":
            self.root.chmod(0o700)

    def tearDown(self):
        self.temp.cleanup()

    def start_server(self, *, connections=8, deadline=10, router=None):
        store = TimerStore(self.root / "state.sqlite3")
        patches = ExitStack()
        patches.enter_context(mock.patch.object(server_module, "MAX_CONNECTIONS", connections))
        patches.enter_context(mock.patch.object(server_module, "CONNECTION_DEADLINE", deadline))
        server = PreviewHTTPServer(("127.0.0.1", 0), handler_for(store, router=router))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(self._stop_server, server, worker, patches)
        return server, worker, patches

    @staticmethod
    def _stop_server(server, worker, patches):
        server.shutdown()
        server.server_close()
        worker.join(timeout=1)
        patches.close()

    @staticmethod
    def raw_request(server, request):
        connection = socket.create_connection(server.server_address, timeout=1)
        connection.settimeout(1)
        try:
            connection.sendall(request)
            chunks = []
            while True:
                try:
                    chunk = connection.recv(4096)
                except ConnectionResetError:
                    break
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            connection.close()

    def test_connection_cap_and_deadline_release_slots_for_health_request(self):
        server, _worker, _patches = self.start_server(connections=2, deadline=0.25)
        partial = b"GET /api/health HTTP/1.1\r\n"
        first = socket.create_connection(server.server_address, timeout=1)
        second = socket.create_connection(server.server_address, timeout=1)
        first.settimeout(1)
        second.settimeout(1)
        first.sendall(partial)
        second.sendall(partial)
        try:
            # Give the accept loop time to account for both partial requests.
            time.sleep(0.05)
            rejected = socket.create_connection(server.server_address, timeout=1)
            rejected.settimeout(1)
            try:
                self.assertEqual(rejected.recv(1), b"")
            except ConnectionResetError:
                pass
            finally:
                rejected.close()

            for stalled in (first, second):
                started = time.monotonic()
                try:
                    data = stalled.recv(1)
                    self.assertEqual(data, b"")
                except ConnectionResetError:
                    pass
                self.assertLess(time.monotonic() - started, 1.0)

            release_deadline = time.monotonic() + 1.0
            slot_returned = False
            while time.monotonic() < release_deadline:
                if server.slots.acquire(blocking=False):
                    server.slots.release()
                    slot_returned = True
                    break
                time.sleep(0.01)
            self.assertTrue(slot_returned, "expired handler threads did not release their connection slots")

            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=1)
            try:
                connection.request("GET", "/api/health", headers={"Host": f"127.0.0.1:{server.server_port}"})
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertIn(b'"mode": "developer-preview"', response.read())
            finally:
                connection.close()
        finally:
            first.close()
            second.close()

    def test_command_extra_field_is_rejected_before_router_dispatch(self):
        router = RecordingRouter()
        server, _worker, _patches = self.start_server(router=router)
        host = f"127.0.0.1:{server.server_port}"
        origin = f"http://{host}"
        body = b'{"text":"synthetic question","unexpected":1}'
        response = self.raw_request(
            server,
            ("POST /api/commands HTTP/1.1\r\n" +
             f"Host: {host}\r\nOrigin: {origin}\r\n" +
             "Content-Type: application/json\r\n" +
             f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode("ascii") + body,
        )

        self.assertTrue(response.startswith(b"HTTP/1.0 400"))
        self.assertEqual(router.calls, [])

    def test_duplicate_host_and_ambiguous_body_framing_are_rejected(self):
        server, _worker, _patches = self.start_server()
        host = f"127.0.0.1:{server.server_port}"
        origin = f"http://{host}"
        body = b"{}"
        prefix = ("POST /api/timers HTTP/1.1\r\n" +
                  f"Host: {host}\r\nOrigin: {origin}\r\n" +
                  "Content-Type: application/json\r\n")

        duplicate_host = self.raw_request(
            server,
            ("GET /api/health HTTP/1.1\r\n" + f"Host: {host}\r\nHost: {host}\r\n" +
             "Connection: close\r\n\r\n").encode("ascii"),
        )
        self.assertTrue(duplicate_host.startswith(b"HTTP/1.0 403"))

        duplicate_lengths = self.raw_request(
            server,
            (prefix + "Content-Length: 2\r\nContent-Length: 2\r\nConnection: close\r\n\r\n").encode("ascii") + body,
        )
        self.assertTrue(duplicate_lengths.startswith(b"HTTP/1.0 400"))

        transfer_encoding = self.raw_request(
            server,
            (prefix + "Content-Length: 2\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n").encode("ascii") + body,
        )
        self.assertTrue(transfer_encoding.startswith(b"HTTP/1.0 400"))

    def test_malformed_utf8_body_returns_generic_400_without_echo(self):
        server, _worker, _patches = self.start_server()
        host = f"127.0.0.1:{server.server_port}"
        origin = f"http://{host}"
        request = (
            f"POST /api/timers HTTP/1.1\r\nHost: {host}\r\nOrigin: {origin}\r\n"
            "Content-Type: application/json\r\nContent-Length: 1\r\nConnection: close\r\n\r\n"
        ).encode("ascii") + b"\xff"

        response = self.raw_request(server, request)

        self.assertTrue(response.startswith(b"HTTP/1.0 400"))
        self.assertIn(b'"error": "Invalid JSON"', response)
        self.assertNotIn(b"\xff", response)


if __name__ == "__main__":
    unittest.main()
