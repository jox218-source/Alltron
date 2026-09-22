"""Loopback-only HTTP service for the developer preview."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlsplit

from . import __version__
from .timers import TimerStore

MAX_BODY = 4096


def handler_for(store: TimerStore):
    class Handler(BaseHTTPRequestHandler):
        server_version = "AlltronPreview/" + __version__

        def log_message(self, format: str, *args: object) -> None:
            # Do not log URL query strings or request bodies.
            print(f"alltron: {self.client_address[0]} {args[1] if len(args) > 1 else ''}")

        def _send(self, status: HTTPStatus, data: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def _json(self, status: HTTPStatus, payload: object) -> None:
            self._send(status, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8")

        def _trusted_host(self) -> bool:
            expected = f"127.0.0.1:{self.server.server_port}"
            if self.headers.get("Host") != expected:
                self._json(HTTPStatus.FORBIDDEN, {"error": "Open Alltron at http://" + expected})
                return False
            return True

        def do_GET(self) -> None:
            if not self._trusted_host():
                return
            path = urlsplit(self.path).path
            if path == "/api/health":
                self._json(HTTPStatus.OK, {
                    "version": __version__, "mode": "developer-preview", "local_timers": "ready",
                    "home_assistant": "not-configured", "codex": "not-configured", "voice": "not-configured",
                })
            elif path == "/api/timers":
                self._json(HTTPStatus.OK, {"timers": store.list()})
            elif path in ("/", "/app.js", "/app.css"):
                asset = "index.html" if path == "/" else path[1:]
                content_type = {"index.html": "text/html; charset=utf-8", "app.js": "text/javascript; charset=utf-8", "app.css": "text/css; charset=utf-8"}[asset]
                self._send(HTTPStatus.OK, files("alltron").joinpath("static", asset).read_bytes(), content_type)
            else:
                self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

        def do_POST(self) -> None:
            if not self._trusted_host():
                return
            path = urlsplit(self.path).path
            if path not in ("/api/timers", "/api/timers/cancel"):
                self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
                return
            origin = self.headers.get("Origin")
            allowed_origin = f"http://127.0.0.1:{self.server.server_port}"
            if origin != allowed_origin:
                self._json(HTTPStatus.FORBIDDEN, {"error": "Open Alltron at " + allowed_origin})
                return
            if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
                self._json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "Expected JSON"})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= MAX_BODY:
                    raise ValueError("Invalid request size")
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise ValueError("Expected a JSON object")
                if path == "/api/timers":
                    seconds = payload.get("seconds")
                    if isinstance(seconds, bool) or not isinstance(seconds, int):
                        raise ValueError("Duration must be whole seconds")
                    label = payload.get("label", "Timer")
                    if not isinstance(label, str):
                        raise ValueError("Label must be text")
                    self._json(HTTPStatus.CREATED, {"timer": store.add(seconds, label)})
                else:
                    timer_id = payload.get("id")
                    if not isinstance(timer_id, str):
                        raise ValueError("Timer ID must be text")
                    if not store.cancel(timer_id):
                        self._json(HTTPStatus.NOT_FOUND, {"error": "Running timer not found"})
                    else:
                        self._json(HTTPStatus.OK, {"cancelled": True})
            except (ValueError, json.JSONDecodeError) as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    return Handler


def make_server(port: int, store_path: Path) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), handler_for(TimerStore(store_path)))


def serve(port: int, store_path: Path) -> None:
    server = make_server(port, store_path)
    print(f"Alltron developer preview: http://127.0.0.1:{server.server_port}")
    print("Press Ctrl+C to stop. This preview does not control Home Assistant or record audio.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
