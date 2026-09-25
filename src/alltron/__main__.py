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
    args = parser.parse_args()
    if args.check:
        print(f"Python: {sys.version.split()[0]}")
        print(f"Data directory: {data_dir()}")
        print("Mode: local developer preview (Home Assistant and audio opt-in; Codex disabled)")
        return
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    serve(port=args.port, store_path=data_dir() / "timers.sqlite3")


if __name__ == "__main__":
    main()
