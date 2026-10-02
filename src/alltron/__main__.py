"""Run the local Alltron developer preview."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .server import serve


def data_dir() -> Path:
    override = os.environ.get("ALLTRON_DATA_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".local" / "share" / "alltron"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Alltron's local developer preview")
    parser.add_argument("--port", type=int, default=8765, help="loopback port (default: 8765)")
    parser.add_argument("--check", action="store_true", help="print local preflight information and exit")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--owner-profile", type=Path, help="private owner.json created by local setup")
    mode.add_argument("--fixture-preview", action="store_true", help="disconnected fictional-data HTTP preview")
    args = parser.parse_args()
    if args.check:
        print(f"Python: {sys.version.split()[0]}")
        print(f"Data directory: {data_dir()}")
        print("Mode: local developer preview (Home Assistant and audio opt-in; Codex disabled)")
        return
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    if not args.owner_profile and not args.fixture_preview:
        parser.error("run owner setup and supply --owner-profile; fixture tests may use --fixture-preview")
    if args.fixture_preview and not os.environ.get("ALLTRON_DATA_DIR"):
        parser.error("fixture preview requires an explicit ALLTRON_DATA_DIR for fictional data")
    storage = args.owner_profile.parent / "data" if args.owner_profile else data_dir()
    try:
        serve(port=args.port, store_path=storage / "timers.sqlite3",
              owner_profile=args.owner_profile, fixture=args.fixture_preview)
    except (OSError, ValueError):
        parser.exit(1, "Alltron stopped: check the private owner profile, certificate and local port.\n")


if __name__ == "__main__":
    main()
