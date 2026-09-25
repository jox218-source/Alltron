"""Narrow Home Assistant service adapter for owner-selected lights and switches."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


_ENTITY = re.compile(r"(light|switch)\.[a-z0-9_]+\Z")
_ALIAS = re.compile(r"[a-z0-9][a-z0-9 -]{0,79}\Z")


def _private_file(path: Path) -> None:
    if not path.is_file() or path.is_symlink():
        raise ValueError("Home Assistant configuration file is missing or is a link")
    if os.name == "posix" and path.stat().st_mode & 0o077:
        raise ValueError("Home Assistant configuration file must be private (chmod 600)")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


class HomeAssistant:
    """The application never accepts arbitrary service names or entity IDs from a command."""

    def __init__(self, port: int, token_file: Path, aliases: dict[str, str]):
        if not 1 <= port <= 65535:
            raise ValueError("Invalid Home Assistant port")
        _private_file(token_file)
        self.port = port
        self.token_file = token_file
        self.aliases: dict[str, str] = {}
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
    def from_file(cls, path: Path) -> HomeAssistant:
        _private_file(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or set(data) != {"port", "token_file", "aliases"}:
            raise ValueError("Invalid Home Assistant configuration")
        if isinstance(data["port"], bool) or not isinstance(data["port"], int):
            raise ValueError("Invalid Home Assistant port")
        if not isinstance(data["token_file"], str) or not isinstance(data["aliases"], dict):
            raise ValueError("Invalid Home Assistant configuration")
        token_file = Path(data["token_file"])
        if not token_file.is_absolute():
            raise ValueError("Home Assistant token path must be absolute")
        return cls(data["port"], token_file, data["aliases"])

    def health(self) -> str:
        return "configured"  # Network and authorization are checked only by an explicit action.

    def switch(self, alias: str, on: bool) -> dict:
        normalized = " ".join(alias.lower().split())
        entity_id = self.aliases.get(normalized)
        if entity_id is None:
            return {"kind": "home-assistant", "status": "not-allowed",
                    "text": "That device is not on Alltron's selected device list."}
        try:
            _private_file(self.token_file)
            token = self.token_file.read_text(encoding="utf-8").strip()
        except (OSError, ValueError):
            return {"kind": "home-assistant", "status": "auth-error",
                    "text": "Home Assistant authorization needs attention."}
        if not token or "\n" in token or "\r" in token:
            return {"kind": "home-assistant", "status": "auth-error",
                    "text": "Home Assistant authorization needs attention."}
        domain = entity_id.split(".", 1)[0]
        service = "turn_on" if on else "turn_off"
        request = Request(
            f"http://127.0.0.1:{self.port}/api/services/{domain}/{service}",
            data=json.dumps({"entity_id": entity_id}).encode("utf-8"),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with build_opener(ProxyHandler({}), _NoRedirect).open(request, timeout=4) as response:
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
