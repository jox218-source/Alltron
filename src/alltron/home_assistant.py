"""Narrow Home Assistant service adapter for owner-selected lights and switches."""

from __future__ import annotations

import json
import re
import ssl
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

from .private_files import read_private_text


_ENTITY = re.compile(r"(light|switch)\.[a-z0-9_]+\Z")
_ALIAS = re.compile(r"[a-z0-9][a-z0-9 -]{0,79}\Z")


def _private_file(path: Path) -> None:
    read_private_text(path, 16 * 1024)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


class HomeAssistant:
    """The application never accepts arbitrary service names or entity IDs from a command."""

    def __init__(self, port: int, token_file: Path, aliases: dict[str, str], ca_file: Path, *, token_supplier=None):
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError("Invalid Home Assistant port")
        _private_file(token_file)
        self.port = port
        self.token_file = token_file
        self.ca_file = ca_file
        self.token_supplier = token_supplier
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.context.load_verify_locations(cadata=read_private_text(ca_file, 16384))
        self.aliases: dict[str, str] = {}
        if not isinstance(aliases, dict) or not 1 <= len(aliases) <= 100:
            raise ValueError("Select between 1 and 100 Home Assistant aliases")
        for alias, entity_id in aliases.items():
            if not isinstance(alias, str) or not isinstance(entity_id, str):
                raise ValueError("Home Assistant aliases must be text")
            normalized = " ".join(alias.lower().split())
            if not _ALIAS.fullmatch(normalized) or not _ENTITY.fullmatch(entity_id):
                raise ValueError("Invalid Home Assistant alias or entity")
            if normalized in self.aliases:
                raise ValueError("Duplicate Home Assistant alias")
            self.aliases[normalized] = entity_id
        if not self.aliases:
            raise ValueError("Select at least one Home Assistant light or switch")

    @classmethod
    def from_file(cls, path: Path, *, token_supplier=None) -> HomeAssistant:
        data = json.loads(read_private_text(path, 16 * 1024))
        if not isinstance(data, dict) or set(data) != {"port", "token_file", "aliases", "ca_file"}:
            raise ValueError("Invalid Home Assistant configuration")
        if isinstance(data["port"], bool) or not isinstance(data["port"], int):
            raise ValueError("Invalid Home Assistant port")
        if not isinstance(data["token_file"], str) or not isinstance(data["aliases"], dict) or not isinstance(data["ca_file"], str):
            raise ValueError("Invalid Home Assistant configuration")
        token_file = Path(data["token_file"])
        if not token_file.is_absolute():
            raise ValueError("Home Assistant token path must be absolute")
        return cls(data["port"], token_file, data["aliases"], Path(data["ca_file"]), token_supplier=token_supplier)

    def health(self) -> str:
        return "configured"  # Network and authorization are checked only by an explicit action.

    def switch(self, alias: str, on: bool) -> dict:
        normalized = " ".join(alias.lower().split())
        entity_id = self.aliases.get(normalized)
        if entity_id is None:
            return {"kind": "home-assistant", "status": "not-allowed",
                    "text": "That device is not on Alltron's selected device list."}
        try:
            token = self.token_supplier() if self.token_supplier else read_private_text(self.token_file, 4096).strip()
        except (OSError, ValueError):
            return {"kind": "home-assistant", "status": "auth-error",
                    "text": "Home Assistant authorization needs attention."}
        if not token or not re.fullmatch(r"[A-Za-z0-9._~-]+", token):
            return {"kind": "home-assistant", "status": "auth-error",
                    "text": "Home Assistant authorization needs attention."}
        domain = entity_id.split(".", 1)[0]
        service = "turn_on" if on else "turn_off"
        request = Request(
            f"https://127.0.0.1:{self.port}/api/services/{domain}/{service}",
            data=json.dumps({"entity_id": entity_id}).encode("utf-8"),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with build_opener(ProxyHandler({}), _NoRedirect, HTTPSHandler(context=self.context)).open(request, timeout=4) as response:
                if response.status not in (200, 201):
                    raise URLError("Unexpected Home Assistant response")
        except HTTPError as exc:
            if exc.code in (401, 403):
                return {"kind": "home-assistant", "status": "auth-error",
                        "text": "Home Assistant authorization needs attention."}
            return {"kind": "home-assistant", "status": "service-error",
                    "text": "Home Assistant could not complete that action."}
        except (OSError, URLError, TimeoutError):
            return {"kind": "home-assistant", "status": "unavailable",
                    "text": "Home Assistant is unavailable. Try again later."}
        return {"kind": "home-assistant", "status": "ok",
                "text": f"Turned {'on' if on else 'off'} {normalized}."}
