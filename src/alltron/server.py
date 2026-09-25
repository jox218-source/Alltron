"""Loopback-only HTTP service for the developer preview."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from . import __version__
from .alarms import AlarmService
from .commands import CommandRouter
from .home_assistant import HomeAssistant
from .timers import TimerStore
from .voice import PersistentMicrophone, SpeechEngine, VoiceConfig, VoiceController, VoiceUnavailable

MAX_BODY = 4096


def handler_for(store: TimerStore, voice: VoiceController | None = None,
                alarms: AlarmService | None = None, router: CommandRouter | None = None):
    router = router or CommandRouter(store, alarm_available=lambda: bool(alarms and alarms.health()["status"] == "ready"))
    voice = voice or VoiceController(None, None, router)

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
                    "local_lists": "ready", "alarm_delivery": alarms.health() if alarms else {"status": "disabled"},
                    "home_assistant": router.home_assistant.health() if router.home_assistant else "not-configured",
                    "codex": "configured" if router.answers else "not-configured",
                    "voice": voice.health(),
                })
            elif path == "/api/timers":
                self._json(HTTPStatus.OK, {"timers": store.list()})
            elif path == "/api/alarms":
                self._json(HTTPStatus.OK, {"alarms": store.list_alarms()})
            elif path == "/api/lists/shopping":
                self._json(HTTPStatus.OK, {"items": store.list_shopping_items()})
            elif path == "/api/voice/events":
                query = urlsplit(self.path).query
                try:
                    after_values = [part[6:] for part in query.split("&") if part.startswith("after=")]
                    after = int(after_values[0]) if len(after_values) == 1 else 0
                    if after < 0:
                        raise ValueError
                except ValueError:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "Invalid event cursor"})
                    return
                self._json(HTTPStatus.OK, {"events": voice.poll(after)})
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
            if path not in ("/api/timers", "/api/timers/cancel", "/api/alarms", "/api/alarms/cancel",
                            "/api/lists/shopping", "/api/lists/shopping/complete", "/api/commands",
                            "/api/voice/start", "/api/voice/stop", "/api/voice/cancel"):
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
                elif path == "/api/timers/cancel":
                    timer_id = payload.get("id")
                    if not isinstance(timer_id, str):
                        raise ValueError("Timer ID must be text")
                    if not store.cancel(timer_id):
                        self._json(HTTPStatus.NOT_FOUND, {"error": "Running timer not found"})
                    else:
                        self._json(HTTPStatus.OK, {"cancelled": True})
                elif path == "/api/alarms":
                    if not alarms or alarms.health()["status"] != "ready":
                        raise VoiceUnavailable("Alarm sound is not configured; no alarm was saved")
                    due_at = payload.get("due_at")
                    if isinstance(due_at, bool) or not isinstance(due_at, (int, float)):
                        raise ValueError("Alarm deadline must be a timestamp")
                    label = payload.get("label", "Alarm")
                    if not isinstance(label, str):
                        raise ValueError("Label must be text")
                    self._json(HTTPStatus.CREATED, {"alarm": store.add_alarm(due_at, label)})
                elif path == "/api/alarms/cancel":
                    alarm_id = payload.get("id")
                    if not isinstance(alarm_id, str):
                        raise ValueError("Alarm ID must be text")
                    if store.cancel_alarm(alarm_id):
                        self._json(HTTPStatus.OK, {"cancelled": True})
                    else:
                        self._json(HTTPStatus.NOT_FOUND, {"error": "Running alarm not found"})
                elif path == "/api/lists/shopping":
                    self._json(HTTPStatus.CREATED, {"item": store.add_shopping_item(payload.get("text"))})
                elif path == "/api/lists/shopping/complete":
                    item_id = payload.get("id")
                    if not isinstance(item_id, str):
                        raise ValueError("Item ID must be text")
                    if store.complete_shopping_item(item_id):
                        self._json(HTTPStatus.OK, {"completed": True})
                    else:
                        self._json(HTTPStatus.NOT_FOUND, {"error": "Open shopping item not found"})
                elif path == "/api/commands":
                    request_id = payload.get("request_id")
                    if request_id is not None:
                        if not isinstance(request_id, str):
                            raise ValueError("Request ID must be text")
                        request_id = str(UUID(request_id))
                    self._json(HTTPStatus.OK, router.execute(payload.get("text"), request_id=request_id))
                elif path == "/api/voice/start":
                    self._json(HTTPStatus.ACCEPTED, {"request_id": voice.begin()})
                elif path == "/api/voice/stop":
                    request_id = payload.get("request_id")
                    if not isinstance(request_id, str):
                        raise ValueError("Voice request ID must be text")
                    voice.end(request_id)
                    self._json(HTTPStatus.ACCEPTED, {"processing": True})
                else:
                    request_id = payload.get("request_id")
                    if not isinstance(request_id, str):
                        raise ValueError("Voice request ID must be text")
                    voice.cancel(request_id)
                    self._json(HTTPStatus.OK, {"cancelled": True})
            except VoiceUnavailable as exc:
                self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": str(exc)})
            except (ValueError, json.JSONDecodeError) as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    return Handler


def make_server(port: int, store_path: Path) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), handler_for(TimerStore(store_path)))


def serve(port: int, store_path: Path) -> None:
    store = TimerStore(store_path)
    config = VoiceConfig.from_env()
    alarms = AlarmService(store, config.audio_output)
    alarms.start()
    # Owner configuration is deliberately outside the repository and disabled by default.
    import os
    ha_path = os.environ.get("ALLTRON_HA_CONFIG")
    ha = HomeAssistant.from_file(Path(ha_path)) if ha_path else None
    router = CommandRouter(store, alarm_available=lambda: alarms.health()["status"] == "ready",
                           home_assistant=ha)
    microphone = PersistentMicrophone(config.audio_input) if config.audio_input else None
    if microphone:
        try:
            microphone.start()
        except (OSError, VoiceUnavailable):
            pass
    engine = SpeechEngine(config) if config.whisper_bin or config.piper_python else None
    voice = VoiceController(microphone, engine, router)
    server = ThreadingHTTPServer(("127.0.0.1", port), handler_for(store, voice, alarms, router))
    print(f"Alltron developer preview: http://127.0.0.1:{server.server_port}")
    print("Press Ctrl+C to stop. Optional voice stays local; HA controls require explicit owner configuration.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        voice.close()
        alarms.close()
