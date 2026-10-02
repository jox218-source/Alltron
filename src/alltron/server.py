"""Loopback-only HTTP service for the developer preview."""

from __future__ import annotations

import json
import socket
import threading
import hmac
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from uuid import UUID

from . import __version__
from .alarms import AlarmService
from .commands import CommandRouter
from .home_assistant import HomeAssistant
from .owner import OwnerAuth, LoginLimited
from .ha_setup import HASetup
from .timers import TimerStore
from .voice import PersistentMicrophone, SpeechEngine, VoiceConfig, VoiceController, VoiceUnavailable

MAX_BODY = 4096
MAX_CONNECTIONS = 8
CONNECTION_DEADLINE = 10


class PreviewHTTPServer(ThreadingHTTPServer):
    """Bound concurrent handlers; loopback remains a trusted-user preview."""

    daemon_threads = True

    def __init__(self, *args, **kwargs):
        self.slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            if getattr(self, "tls_context", None):
                request.do_handshake()
            super().process_request_thread(request, client_address)
        except OSError:
            self.shutdown_request(request)
        finally:
            self.slots.release()

    def get_request(self):
        request, address = super().get_request()
        if getattr(self, "tls_context", None):
            request.settimeout(3)
            try:
                request = self.tls_context.wrap_socket(request, server_side=True, do_handshake_on_connect=False)
            except OSError:
                request.close()
                raise
        return request, address


def handler_for(store: TimerStore, voice: VoiceController | None = None,
                alarms: AlarmService | None = None, router: CommandRouter | None = None,
                auth: OwnerAuth | None = None, ha_setup: HASetup | None = None):
    router = router or CommandRouter(store, alarm_available=lambda: bool(alarms and alarms.health()["status"] == "ready"))
    voice = voice or VoiceController(None, None, router)

    class Handler(BaseHTTPRequestHandler):
        server_version = "AlltronPreview/" + __version__

        def setup(self):
            self.request.settimeout(min(3, CONNECTION_DEADLINE))
            super().setup()
            def expire():
                try:
                    self.request.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                self.request.close()
            self.deadline = threading.Timer(CONNECTION_DEADLINE, expire)
            self.deadline.daemon = True
            self.deadline.start()

        def handle(self):
            try:
                super().handle()
            except (ConnectionError, TimeoutError):
                self.close_connection = True

        def finish(self):
            try:
                super().finish()
            finally:
                self.deadline.cancel()

        def log_message(self, format: str, *args: object) -> None:
            # BaseHTTPRequestHandler also logs malformed request text through
            # this method. Only a numeric HTTP status is safe to retain.
            value = str(args[1]) if len(args) > 1 else ""
            status = value if len(value) == 3 and value.isascii() and value.isdigit() else "closed"
            print(f"alltron: request {status}")

        def _send(self, status: HTTPStatus, data: bytes, content_type: str, cookie: str | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            if cookie:
                self.send_header("Set-Cookie", cookie)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def _json(self, status: HTTPStatus, payload: object, cookie: str | None = None) -> None:
            self._send(status, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8", cookie)

        def _authorized(self) -> bool:
            return auth is None or auth.authorized(self.headers.get("Cookie"))

        def _require_owner(self) -> bool:
            if self._authorized():
                return True
            self._json(HTTPStatus.UNAUTHORIZED, {"error": "Unlock Alltron to continue"})
            return False

        def _trusted_host(self) -> bool:
            expected = f"127.0.0.1:{self.server.server_port}"
            if self.headers.get_all("Host") != [expected]:
                scheme = "https" if auth else "http"
                self._json(HTTPStatus.FORBIDDEN, {"error": "Open Alltron at " + scheme + "://" + expected})
                return False
            return True

        def do_GET(self) -> None:
            if not self._trusted_host():
                return
            path = urlsplit(self.path).path
            if path == "/auth/ha-callback":
                if not auth or not ha_setup:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "HA setup is unavailable"})
                    return
                if not self._require_owner():
                    return
                try:
                    query = parse_qs(urlsplit(self.path).query, max_num_fields=2, strict_parsing=True)
                    if set(query) != {"state", "code"} or any(len(values) != 1 for values in query.values()):
                        raise ValueError("Invalid callback")
                    ha_setup.exchange(auth.cookie_identity(self.headers.get("Cookie")), query["state"][0], query["code"][0])
                    self.send_response(HTTPStatus.SEE_OTHER)
                    self.send_header("Location", "/")
                    self.send_header("Content-Length", "0")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Referrer-Policy", "no-referrer")
                    self.end_headers()
                except (OSError, ValueError):
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "HA authorization stopped; restart setup from Alltron"})
                return
            if path == "/api/session":
                self._json(HTTPStatus.OK, {"authenticated": self._authorized(),
                                          "csrf": auth.csrf(self.headers.get("Cookie")) if auth else None})
                return
            if path.startswith("/api/") and path != "/api/health" and not self._require_owner():
                return
            if path == "/api/setup":
                self._json(HTTPStatus.OK, ha_setup.status() if ha_setup else {"home_assistant": "endpoint-not-installed", "codex": "disabled-pending-isolation-acceptance"})
            elif path == "/api/setup/ha/devices":
                try:
                    if not ha_setup:
                        raise ValueError("Endpoint missing")
                    self._json(HTTPStatus.OK, ha_setup.devices())
                except (OSError, ValueError):
                    self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "HA connection needs attention; check local service and authorization"})
            elif path == "/api/health":
                if auth and not self._authorized():
                    self._json(HTTPStatus.OK, {"mode": "owner", "status": "locked"})
                    return
                self._json(HTTPStatus.OK, {
                    "version": __version__, "mode": "owner" if auth else "developer-preview", "local_timers": "ready",
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
                            "/api/voice/start", "/api/voice/stop", "/api/voice/cancel", "/api/login", "/api/logout",
                            "/api/setup/ha/start", "/api/setup/ha/select", "/api/setup/ha/revoke", "/api/setup/ha/disconnect"):
                self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
                return
            origin = self.headers.get("Origin")
            allowed_origin = f"{'https' if auth else 'http'}://127.0.0.1:{self.server.server_port}"
            if origin != allowed_origin or self.headers.get_all("Origin") != [allowed_origin]:
                self._json(HTTPStatus.FORBIDDEN, {"error": "Open Alltron at " + allowed_origin})
                return
            if path != "/api/login" and not self._require_owner():
                return
            if auth and path != "/api/login":
                csrf = auth.csrf(self.headers.get("Cookie"))
                supplied = self.headers.get_all("X-Alltron-CSRF", [])
                if len(supplied) != 1 or not csrf or not supplied[0].isascii() or not hmac.compare_digest(csrf, supplied[0]):
                    self._json(HTTPStatus.FORBIDDEN, {"error": "Refresh the page and retry"})
                    return
            if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
                self._json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "Expected JSON"})
                return
            try:
                if self.headers.get("Transfer-Encoding") is not None or len(self.headers.get_all("Content-Length", [])) != 1:
                    raise ValueError("Invalid request framing")
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= MAX_BODY:
                    raise ValueError("Invalid request size")
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise ValueError("Expected a JSON object")
                fields = {
                    "/api/timers": {"seconds", "label"}, "/api/timers/cancel": {"id"},
                    "/api/alarms": {"due_at", "label"}, "/api/alarms/cancel": {"id"},
                    "/api/lists/shopping": {"text"}, "/api/lists/shopping/complete": {"id"},
                    "/api/commands": {"text", "request_id"}, "/api/voice/start": set(),
                    "/api/voice/stop": {"request_id"}, "/api/voice/cancel": {"request_id"},
                    "/api/login": {"password"}, "/api/logout": set(),
                    "/api/setup/ha/start": set(), "/api/setup/ha/select": {"aliases"}, "/api/setup/ha/revoke": set(),
                    "/api/setup/ha/disconnect": set(),
                }
                if set(payload) - fields[path]:
                    raise ValueError("Unexpected request fields")
                if path.startswith("/api/setup/ha/"):
                    if not auth or not ha_setup:
                        raise ValueError("Install the local HA endpoint before setup")
                    if path.endswith("/start"):
                        result = ha_setup.begin(auth.cookie_identity(self.headers.get("Cookie")), allowed_origin)
                    elif path.endswith("/select"):
                        router.home_assistant = ha_setup.select(payload.get("aliases"))
                        result = ha_setup.status()
                    else:
                        # A failed/partial cleanup must never leave a live adapter.
                        router.home_assistant = None
                        result = ha_setup.disconnect() if path.endswith("/disconnect") else ha_setup.revoke()
                    self._json(HTTPStatus.OK, result)
                elif path == "/api/login":
                    if auth is None:
                        self._json(HTTPStatus.OK, {"authenticated": True})
                        return
                    cookie = auth.login(payload.get("password"), self.headers.get("Cookie"))
                    if not cookie:
                        self._json(HTTPStatus.UNAUTHORIZED, {"error": "Unable to unlock; check your local owner password"})
                        return
                    self._json(HTTPStatus.OK, {"authenticated": True}, cookie)
                elif path == "/api/logout":
                    self._json(HTTPStatus.OK, {"authenticated": False}, auth.logout(self.headers.get("Cookie")) if auth else None)
                elif path == "/api/timers":
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
            except LoginLimited as exc:
                self._json(HTTPStatus.TOO_MANY_REQUESTS, {"error": str(exc)})
            except (UnicodeError, json.JSONDecodeError):
                self._json(HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON"})
            except ValueError as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": "HA setup needs attention; check service and authorization" if path.startswith("/api/setup/") else str(exc)})
            except OSError:
                self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "Local connection unavailable; check service and authorization"})

    return Handler


def make_server(port: int, store_path: Path) -> ThreadingHTTPServer:
    return PreviewHTTPServer(("127.0.0.1", port), handler_for(TimerStore(store_path)))


def serve(port: int, store_path: Path, *, owner_profile: Path | None = None, fixture: bool = False) -> None:
    if not owner_profile and not fixture:
        raise ValueError("Run local owner setup first, or use --fixture-preview for disconnected tests")
    auth = OwnerAuth(owner_profile) if owner_profile else None
    context = auth.context() if auth else None
    ha_setup = HASetup.from_profile(owner_profile.parent) if owner_profile else None
    ha = ha_setup.adapter() if ha_setup else None
    store = TimerStore(store_path)
    config = VoiceConfig() if fixture else VoiceConfig.from_env()
    alarms = AlarmService(store, config.audio_output)
    router = CommandRouter(store, alarm_available=lambda: alarms.health()["status"] == "ready",
                           home_assistant=ha)
    microphone = PersistentMicrophone(config.audio_input) if config.audio_input else None
    engine = SpeechEngine(config) if config.whisper_bin or config.piper_python else None
    voice = VoiceController(microphone, engine, router)
    server = PreviewHTTPServer(("127.0.0.1", port), handler_for(store, voice, alarms, router, auth, ha_setup))
    if auth:
        server.tls_context = context
    print(f"Alltron: {'https' if auth else 'http'}://127.0.0.1:{server.server_port}")
    print("Press Ctrl+C to stop. Optional voice stays local; HA controls require explicit owner configuration.")
    try:
        alarms.start()
        if microphone:
            try:
                microphone.start()
            except (OSError, VoiceUnavailable):
                pass
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        voice.close()
        alarms.close()
