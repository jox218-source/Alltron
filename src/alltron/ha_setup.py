"""Owner-session-bound Home Assistant OAuth over a verified loopback TLS endpoint."""

from __future__ import annotations

import json
import math
import re
import secrets
import socket
import ssl
import threading
import time
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

from .home_assistant import HomeAssistant, _NoRedirect, _ENTITY
from .private_files import checked_path, read_private_text
from .setup import private_write

TOKEN = re.compile(r"[A-Za-z0-9._~-]{1,4096}\Z")


class HASetup:
    def __init__(self, root: Path, port: int, ca_file: Path):
        checked_path(root, directory=True)
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError("Invalid HA port")
        self.root, self.port, self.ca_file = root, port, ca_file
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.context.load_verify_locations(cadata=read_private_text(ca_file, 16384))
        self.pending: dict[str, tuple[str, str, float]] = {}
        self.lock = threading.RLock()

    @classmethod
    def from_profile(cls, root: Path):
        path = root / "ha-endpoint.json"
        if not path.exists():
            return None
        data = json.loads(read_private_text(path, 4096))
        if not isinstance(data, dict) or set(data) != {"port", "ca_file"} or not isinstance(data["ca_file"], str):
            raise ValueError("Invalid HA endpoint configuration")
        return cls(root, data["port"], Path(data["ca_file"]))

    def _request(self, path: str, *, form: dict | None = None, token: str | None = None):
        if path not in {"/auth/token", "/auth/revoke", "/api/states"}:
            raise ValueError("Unsupported setup request")
        headers = {}
        if form is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        if token is not None:
            if not TOKEN.fullmatch(token):
                raise ValueError("Invalid authorization")
            headers["Authorization"] = "Bearer " + token
        request = Request(f"https://127.0.0.1:{self.port}{path}",
                          data=urlencode(form).encode() if form is not None else None, headers=headers)
        with build_opener(ProxyHandler({}), _NoRedirect, HTTPSHandler(context=self.context)).open(request, timeout=4) as response:
            if response.status != 200:
                raise ValueError("HA setup request was refused")
            body = response.read(1024 * 1024 + 1)
        if len(body) > 1024 * 1024:
            raise ValueError("HA setup response exceeded its limit")
        return json.loads(body) if body else None

    @staticmethod
    def _origin(origin: str) -> str:
        parsed = urlsplit(origin)
        if (parsed.scheme != "https" or parsed.hostname != "127.0.0.1" or parsed.username
                or parsed.password or not parsed.port or parsed.path or parsed.query or parsed.fragment):
            raise ValueError("Invalid local callback origin")
        return origin + "/"

    def begin(self, owner_session: str, origin: str) -> dict:
        client = self._origin(origin)
        # Verify service identity before directing an owner to authenticate there.
        with socket.create_connection(("127.0.0.1", self.port), timeout=4) as connection:
            with self.context.wrap_socket(connection, server_hostname="127.0.0.1"):
                pass
        with self.lock:
            now = time.monotonic()
            self.pending = {state: value for state, value in self.pending.items() if value[2] > now}
            if len(self.pending) >= 8:
                raise ValueError("Setup is busy; retry after five minutes")
            state = secrets.token_urlsafe(32)
            self.pending[state] = owner_session, client, now + 300
        return {"url": f"https://127.0.0.1:{self.port}/auth/authorize?" + urlencode(
            {"client_id": client, "redirect_uri": client + "auth/ha-callback", "state": state})}

    def exchange(self, owner_session: str, state: str, code: str) -> dict:
        if (not isinstance(state, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", state)
                or not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,512}", code)):
            raise ValueError("Invalid authorization callback")
        with self.lock:
            entry = self.pending.pop(state, None)
            if not entry or entry[0] != owner_session or entry[2] < time.monotonic():
                raise ValueError("Authorization expired; start HA setup again")
            result = self._request("/auth/token", form={"grant_type": "authorization_code", "code": code,
                                                       "client_id": entry[1]})
            self._save_session(result, entry[1])
        return self.status()

    def _save_session(self, result, client: str, refresh: str | None = None) -> None:
        if (not isinstance(result, dict) or result.get("token_type", "").lower() != "bearer"
                or not isinstance(result.get("access_token"), str) or not TOKEN.fullmatch(result["access_token"])
                or isinstance(result.get("expires_in"), bool) or not isinstance(result.get("expires_in"), int)
                or not 1 <= result["expires_in"] <= 86400):
            raise ValueError("Invalid HA authorization response")
        refresh = result.get("refresh_token", refresh)
        if not isinstance(refresh, str) or not TOKEN.fullmatch(refresh):
            raise ValueError("Invalid HA authorization response")
        private_write(self.root / "ha-access.token", result["access_token"])
        private_write(self.root / "ha-session.json", json.dumps({"client": client, "refresh": refresh,
                                                                "expires": time.time() + result["expires_in"]}))

    def token(self) -> str:
        with self.lock:
            session = json.loads(read_private_text(self.root / "ha-session.json", 16384))
            if (not isinstance(session, dict) or set(session) != {"client", "refresh", "expires"}
                    or not isinstance(session["client"], str) or not isinstance(session["refresh"], str)
                    or not TOKEN.fullmatch(session["refresh"]) or isinstance(session["expires"], bool)
                    or not isinstance(session["expires"], (int, float)) or not math.isfinite(session["expires"])):
                raise ValueError("HA authorization needs attention")
            self._origin(session["client"].removesuffix("/"))
            if session["expires"] < time.time() + 60:
                result = self._request("/auth/token", form={"grant_type": "refresh_token", "refresh_token": session["refresh"],
                                                           "client_id": session["client"]})
                self._save_session(result, session["client"], session["refresh"])
            token = read_private_text(self.root / "ha-access.token", 4096).strip()
            if not TOKEN.fullmatch(token):
                raise ValueError("HA authorization needs attention")
            return token

    def devices(self) -> dict:
        states = self._request("/api/states", token=self.token())
        if not isinstance(states, list) or len(states) > 5000:
            raise ValueError("Invalid HA device response")
        devices = []
        for state in states:
            if not isinstance(state, dict) or not isinstance(state.get("entity_id"), str) or not _ENTITY.fullmatch(state["entity_id"]):
                continue
            attributes = state.get("attributes")
            name = attributes.get("friendly_name") if isinstance(attributes, dict) else None
            devices.append({"entity_id": state["entity_id"], "name": name[:80] if isinstance(name, str) else state["entity_id"]})
        return {"devices": devices[:1000]}

    def select(self, aliases: dict) -> HomeAssistant:
        known = {device["entity_id"] for device in self.devices()["devices"]}
        if not isinstance(aliases, dict) or any(not isinstance(value, str) or value not in known for value in aliases.values()):
            raise ValueError("Select only listed lights and switches")
        adapter = HomeAssistant(self.port, self.root / "ha-access.token", aliases, self.ca_file, token_supplier=self.token)
        private_write(self.root / "ha.json", json.dumps({"port": self.port, "ca_file": str(self.ca_file),
                                                        "token_file": str(self.root / "ha-access.token"), "aliases": adapter.aliases}))
        return adapter

    def adapter(self):
        if not (self.root / "ha.json").exists():
            return None
        return HomeAssistant.from_file(self.root / "ha.json", token_supplier=self.token)

    def revoke(self) -> dict:
        with self.lock:
            self.token()  # Validate saved session before using its refresh credential.
            session = json.loads(read_private_text(self.root / "ha-session.json", 16384))
            self._request("/auth/revoke", form={"token": session["refresh"]})
            self.pending.clear()
            for name in ("ha.json", "ha-session.json", "ha-access.token"):
                path = self.root / name
                if path.exists():
                    read_private_text(path, 16384)
                    path.unlink()
        return self.status()

    def status(self) -> dict:
        return {"home_assistant": "selected" if (self.root / "ha.json").exists() else
                "authorized" if (self.root / "ha-session.json").exists() else "needs-authorization",
                "codex": "disabled-pending-isolation-acceptance"}
