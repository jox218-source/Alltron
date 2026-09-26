"""Local developer preview staging, startup and code rollback; never a Pi installer."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

if __package__:
    from .build_release import ReleaseError, read_archive_bytes, verified_payloads
    from . import preview_backup
else:
    from build_release import ReleaseError, read_archive_bytes, verified_payloads
    import preview_backup

STATE = "installation.json"
FORMAT = "alltron-preview-1"
MIN_FREE = 64 * 1024 * 1024
DIGEST = re.compile(r"[0-9a-f]{64}")


class InstallError(Exception):
    pass


def local_path(path: Path) -> None:
    """Reject symlinks and Windows junctions before reading or writing a path."""
    for part in reversed((path, *path.parents)):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 1024:
            raise InstallError("Choose a path without symbolic links or junctions")


def checked_root(root: Path) -> Path:
    try:
        user_home = Path.home()
    except RuntimeError:
        user_home = None  # Deliberately absent in the restricted preview process.
    if not root.is_absolute() or ".." in root.parts or root == Path(root.anchor) or root == user_home:
        raise InstallError("Choose an absolute preview folder below an existing parent")
    local_path(root)
    if not root.parent.is_dir() or root.exists() and not root.is_dir():
        raise InstallError("The preview parent must exist and the target must be a folder")
    if root.exists() and os.name == "posix":
        info = root.stat()
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise InstallError("Use an owner-only preview folder with mode 0700")
    return root


def regular_file(path: Path) -> None:
    local_path(path)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise InstallError("Preview files must be ordinary files without links")


def require_user() -> None:
    if os.name == "posix" and os.geteuid() == 0:
        raise InstallError("Run the preview manager as an ordinary user, without sudo")


def data_directory(root: Path) -> Path:
    data = root / "data"
    local_path(data)
    if not data.is_dir():
        raise InstallError("Run init again to complete the managed folder layout")
    if os.name == "posix" and (data.stat().st_uid != os.getuid() or stat.S_IMODE(data.stat().st_mode) & 0o077):
        raise InstallError("Use an owner-only data folder with mode 0700")
    for suffix in ("", "-wal", "-shm", "-journal"):
        database = data / ("timers.sqlite3" + suffix)
        local_path(database)
        if database.exists():
            regular_file(database)
    return data


def backup_directory(root: Path, *, create: bool = False) -> Path:
    folder = root / "backups"
    local_path(folder)
    if create:
        folder.mkdir(mode=0o700, exist_ok=True)
    if folder.exists():
        if not folder.is_dir():
            raise InstallError("The backup destination must be a private folder")
        info = folder.stat()
        if os.name == "posix" and (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077):
            raise InstallError("Use an owner-only backup folder with mode 0700")
    return folder


def no_database_sidecars(database: Path) -> None:
    if any(database.with_name(database.name + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
        raise InstallError("SQLite sidecars are present; close other database users and recover them before restoring")


def snapshot_locked(root: Path, *, preserve_invalid: bool = False) -> dict:
    state = load_state(root)
    if not state["current"]:
        raise InstallError("Install a preview archive before backing up its data")
    database = data_directory(root) / "timers.sqlite3"
    if not database.exists():
        raise InstallError("No application database exists yet")
    folder = backup_directory(root, create=True)
    try:
        return preview_backup.create_snapshot(database, folder, state["current"])
    except preview_backup.InvalidDatabase:
        if not preserve_invalid:
            raise
        no_database_sidecars(database)
        return preview_backup.write_archive(folder, preview_backup.bounded_read(database),
                                            state["current"], "preserved-original")


def backup(root: Path) -> dict:
    require_user()
    with locked(root):
        return snapshot_locked(root)


def backups(root: Path) -> dict:
    with locked(root):
        folder = backup_directory(root)
        result = []
        if folder.exists():
            for path in sorted(folder.glob("*.zip")):
                regular_file(path)
                metadata, _ = preview_backup.read_archive(path, path.stem)
                result.append(metadata)
        return {"backups": result}


def restore(root: Path, identity: str, *, replace_data: bool = False) -> dict:
    require_user()
    if not replace_data:
        raise InstallError("Restoring replaces application state; supply --replace-data to continue")
    if not preview_backup.IDENTITY.fullmatch(identity):
        raise InstallError("Choose a backup ID from the backups command")
    with locked(root):
        state = load_state(root)
        path = backup_directory(root) / (identity + ".zip")
        regular_file(path)
        metadata, payload = preview_backup.read_archive(path, identity)
        if metadata["kind"] != "snapshot":
            raise InstallError("Preserved originals are recovery material, not validated restore snapshots")
        if metadata["release_sha256"] != state["current"]:
            raise InstallError("Select the exact release recorded by this backup before restoring")
        release_on_disk(root, state["current"])
        database = data_directory(root) / "timers.sqlite3"
        no_database_sidecars(database)
        with tempfile.NamedTemporaryFile(dir=database.parent, prefix=".restore-", delete=False) as stream:
            pending = Path(stream.name)
            try:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            except BaseException:
                stream.close()
                pending.unlink(missing_ok=True)
                raise
        try:
            preview_backup.validate_database(pending)
            safety = snapshot_locked(root, preserve_invalid=True) if database.exists() else None
            # Read-only SQLite access can create WAL/SHM files for a WAL-mode
            # main file. Never replace that main file while sidecars remain.
            no_database_sidecars(database)
            os.replace(pending, database)
            preview_backup.sync_directory(database.parent)
        finally:
            pending.unlink(missing_ok=True)
        return {"status": "restored", "backup_id": identity, "safety_backup": safety}


def preserve_before_switch(root: Path, state: dict) -> dict | None:
    database = data_directory(root) / "timers.sqlite3"
    if state["current"] and database.exists():
        return snapshot_locked(root, preserve_invalid=True)
    return None


def preflight(root: Path) -> dict:
    checks = []

    def add(code, ok, remedy, warning=False):
        checks.append({"code": code, "status": "pass" if ok else "warning" if warning else "blocked",
                       "message": "Ready" if ok else remedy})

    add("python", sys.version_info >= (3, 11), "Install Python 3.11 or newer")
    add("platform", platform.system() in ("Windows", "Linux"), "Use Windows or Linux for this developer preview")
    add("ordinary_user", os.name != "posix" or os.geteuid() != 0, "Run without sudo as an ordinary user")
    try:
        checked_root(root)
        if root.exists():
            if (root / STATE).exists():
                load_state(root)
                data_directory(root)
            elif any(path.name != ".lock" for path in root.iterdir()):
                raise InstallError("Choose an empty or managed preview folder")
        add("destination", True, "")
        probe = root if root.exists() else root.parent
        add("free_space", shutil.disk_usage(probe).free >= MIN_FREE, "Free at least 64 MiB on the destination disk")
        add("write_access", os.access(probe, os.W_OK | os.X_OK), "Choose a folder you own and can write")
    except (InstallError, OSError):
        add("destination", False, "Choose an absolute, private folder with an existing parent and no links")
    try:
        ZoneInfo("America/New_York")
        add("iana_timezones", True, "")
    except ZoneInfoNotFoundError:
        add("iana_timezones", False, "Install IANA time-zone data before time-zone integration testing", warning=True)
    return {"profile": "developer-preview", "ready": all(c["status"] != "blocked" for c in checks),
            "appliance_ready": False, "checks": checks}


@contextmanager
def locked(root: Path, *, initializing: bool = False):
    checked_root(root)
    if not root.is_dir():
        raise InstallError("Initialize the preview folder first")
    if not initializing:
        load_state(root)
    path = root / ".lock"
    if path.exists():
        regular_file(path)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(descriptor, "r+b") as stream:
        if stream.seek(0, os.SEEK_END) == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise InstallError("Preview is busy; stop its managed run or wait for the other operation") from None
        try:
            yield
        finally:
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def load_state(root: Path) -> dict:
    try:
        regular_file(root / STATE)
        with (root / STATE).open("rb") as stream:
            state = json.loads(stream.read(4097))
        if (set(state) != {"format", "current", "previous"} or state["format"] != FORMAT
                or any(value is not None and (not isinstance(value, str) or not DIGEST.fullmatch(value))
                       for value in (state["current"], state["previous"]))):
            raise ValueError
        return state
    except (OSError, ValueError, TypeError):
        raise InstallError("Folder is not an intact managed preview; choose a new empty folder") from None


def write_state(root: Path, state: dict) -> None:
    local_path(root / STATE)
    with tempfile.NamedTemporaryFile(dir=root, prefix=".pointer-", delete=False) as stream:
        pending = Path(stream.name)
        stream.write((json.dumps(state, sort_keys=True) + "\n").encode())
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.replace(pending, root / STATE)
        if os.name == "posix":
            descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        pending.unlink(missing_ok=True)


def initialize(root: Path) -> dict:
    require_user()
    checked_root(root)
    if root.exists() and not (root / STATE).exists() and any(path.name != ".lock" for path in root.iterdir()):
        raise InstallError("Initialize only an empty preview folder")
    root.mkdir(mode=0o700, exist_ok=True)
    with locked(root, initializing=True):
        if (root / STATE).exists():
            load_state(root)
        else:
            if any(path.name != ".lock" for path in root.iterdir()):
                raise InstallError("Initialize only an empty preview folder")
            write_state(root, {"format": FORMAT, "current": None, "previous": None})
        for name in ("releases", "data"):
            path = root / name
            local_path(path)
            path.mkdir(mode=0o700, exist_ok=True)
        data_directory(root)
        return {"status": "initialized", "profile": "developer-preview"}


def archive_snapshot(archive: Path, expected: str) -> tuple[bytes, dict, dict[str, bytes]]:
    if not isinstance(expected, str) or not DIGEST.fullmatch(expected):
        raise InstallError("Supply the complete lowercase SHA-256 from a trusted source")
    data = read_archive_bytes(archive)
    if hashlib.sha256(data).hexdigest() != expected:
        raise InstallError("Archive checksum does not match; obtain a fresh trusted copy")
    manifest, payloads = verified_payloads(data)
    required = {"src/alltron/__init__.py", "src/alltron/server.py", "src/alltron/__main__.py"}
    if not required.issubset(payloads):
        raise InstallError("Archive does not contain the Alltron preview application")
    return data, manifest, payloads


def release_on_disk(root: Path, identity: str) -> tuple[Path, dict]:
    release = root / "releases" / identity
    local_path(release)
    regular_file(release / "source.zip")
    _, manifest, payloads = archive_snapshot(release / "source.zip", identity)
    content = release / "content"
    local_path(content)
    expected_dirs = {str(parent) for name in payloads for parent in Path(name).parents if str(parent) != "."}
    found = set()
    for base, directories, files in os.walk(content, followlinks=False):
        for name in directories:
            child = Path(base) / name
            local_path(child)
            if str(child.relative_to(content)) not in expected_dirs:
                raise InstallError("Installed source contains unexpected directories")
        for name in files:
            child = Path(base) / name
            regular_file(child)
            relative = child.relative_to(content).as_posix()
            if relative not in payloads or child.stat().st_size != len(payloads[relative]) or child.read_bytes() != payloads[relative]:
                raise InstallError("Installed source was changed; restore a trusted release")
            found.add(relative)
    if found != set(payloads):
        raise InstallError("Installed source is incomplete")
    return content, manifest


def child_environment() -> dict:
    # Integrations and provider credentials are never inherited by this preview.
    if os.name != "nt":
        return {}
    return {key: value for key, value in os.environ.items() if key.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP"}}


SMOKE = """
import json, pathlib, sys, threading, urllib.request
sys.path.insert(0, sys.argv[1])
from alltron.server import make_server
server = make_server(0, pathlib.Path(sys.argv[2]) / 'timers.sqlite3')
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
try:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open('http://127.0.0.1:%s/api/health' % server.server_port, timeout=5) as response:
        health = json.load(response)
    assert health['mode'] == 'developer-preview' and health['local_timers'] == 'ready'
    assert health['home_assistant'] == 'not-configured' and health['codex'] == 'not-configured'
finally:
    server.shutdown()
    server.server_close()
    thread.join(5)
"""


def smoke_test(content: Path, root: Path) -> None:
    try:
        for source in content.rglob("*.py"):
            compile(source.read_bytes(), source.relative_to(content).as_posix(), "exec")
        with tempfile.TemporaryDirectory(dir=root, prefix=".smoke-") as directory:
            result = subprocess.run([sys.executable, "-I", "-B", "-c", SMOKE, str(content / "src"), directory],
                                    cwd=directory, env=child_environment(), stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
            if result.returncode:
                raise InstallError("Candidate failed its local health check; the selected release is unchanged")
    except (SyntaxError, subprocess.TimeoutExpired):
        raise InstallError("Candidate failed syntax or startup checks; the selected release is unchanged") from None


def install(root: Path, archive: Path, expected: str) -> dict:
    require_user()
    data, manifest, payloads = archive_snapshot(archive, expected)
    if not preflight(root)["ready"]:
        raise InstallError("Preflight is blocked; run preflight to see the remedies")
    with locked(root):
        state = load_state(root)
        if state["current"]:
            release_on_disk(root, state["current"])
        releases = root / "releases"
        local_path(releases)
        if not releases.is_dir():
            raise InstallError("Run init again to complete the managed folder layout")
        destination = releases / expected
        local_path(destination)
        if destination.exists():
            content, manifest = release_on_disk(root, expected)
            smoke_test(content, root)
        else:
            # This private staging folder is the only tree this operation removes.
            with tempfile.TemporaryDirectory(dir=releases, prefix=".stage-") as directory:
                staged = Path(directory)
                (staged / "source.zip").write_bytes(data)
                for name, payload in payloads.items():
                    target = staged / "content" / name
                    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    with target.open("xb") as stream:
                        stream.write(payload)
                        stream.flush()
                        os.fsync(stream.fileno())
                smoke_test(staged / "content", root)
                os.replace(staged, destination)
        safety = None
        if state["current"] != expected:
            safety = preserve_before_switch(root, state)
            write_state(root, {"format": FORMAT, "current": expected, "previous": state["current"]})
        return {"status": "installed", "version": manifest["version"], "commit": manifest["commit"],
                "archive_sha256": expected, "data_backup": safety}


def rollback(root: Path) -> dict:
    require_user()
    with locked(root):
        state = load_state(root)
        if state["previous"] is None:
            raise InstallError("No previous release is available")
        content, manifest = release_on_disk(root, state["previous"])
        smoke_test(content, root)
        safety = preserve_before_switch(root, state)
        write_state(root, {"format": FORMAT, "current": state["previous"], "previous": state["current"]})
        return {"status": "rolled_back", "version": manifest["version"], "commit": manifest["commit"], "data_backup": safety}


def status(root: Path) -> dict:
    with locked(root):
        state = load_state(root)
        result = {"profile": "developer-preview", "current": None, "previous": None}
        for key in ("current", "previous"):
            if state[key]:
                _, manifest = release_on_disk(root, state[key])
                result[key] = {"version": manifest["version"], "commit": manifest["commit"], "archive_sha256": state[key]}
        return result


def serve_locked(root: Path, port: int) -> None:
    """The serving process owns the lock, including if its launcher exits."""
    require_user()
    if not 1 <= port <= 65535:
        raise InstallError("Choose a port from 1 to 65535")
    with locked(root):
        state = load_state(root)
        if not state["current"]:
            raise InstallError("Install a preview archive first")
        content, _ = release_on_disk(root, state["current"])
        data = data_directory(root)
        if any(name == "alltron" or name.startswith("alltron.") for name in sys.modules):
            raise InstallError("Start the managed preview in a fresh Python process")
        sys.path.insert(0, str(content / "src"))
        from alltron.server import serve
        serve(port=port, store_path=data / "timers.sqlite3")


def run(root: Path, port: int) -> int:
    require_user()
    checked_root(root)
    if not 1 <= port <= 65535:
        raise InstallError("Choose a port from 1 to 65535")
    program = """
import pathlib,sys
sys.path.insert(0, sys.argv[1])
from tools.preview_install import serve_locked, InstallError, ReleaseError
try:
    serve_locked(pathlib.Path(sys.argv[2]), int(sys.argv[3]))
except (InstallError, ReleaseError) as error:
    print('Preview operation stopped: ' + str(error), flush=True)
    sys.exit(1)
except (OSError, ValueError):
    print('Preview stopped: check its port and private data permissions', flush=True)
    sys.exit(1)
"""
    process = subprocess.Popen([sys.executable, "-I", "-B", "-c", program,
                                str(Path(__file__).resolve().parents[1]), str(root), str(port)],
                               cwd=root, env=child_environment(), stderr=subprocess.DEVNULL)
    try:
        code = process.wait()
        if code:
            raise InstallError("Preview did not complete normally; check its setup and any message above")
        return code
    except KeyboardInterrupt:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "preflight", "install", "status", "rollback", "run", "backup", "backups", "restore"):
        command = commands.add_parser(name)
        command.add_argument("--root", type=Path, required=True)
        if name == "install":
            command.add_argument("--archive", type=Path, required=True)
            command.add_argument("--sha256", required=True)
        if name == "run":
            command.add_argument("--port", type=int, default=8765)
        if name == "restore":
            command.add_argument("--backup", required=True)
            command.add_argument("--replace-data", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "run":
            raise SystemExit(run(args.root, args.port))
        if args.command == "install":
            result = install(args.root, args.archive, args.sha256)
        elif args.command == "restore":
            result = restore(args.root, args.backup, replace_data=args.replace_data)
        else:
            result = {"init": initialize, "preflight": preflight, "status": status, "rollback": rollback,
                      "backup": backup, "backups": backups}[args.command](args.root)
        print(json.dumps(result, sort_keys=True))
        if args.command == "preflight" and not result["ready"]:
            raise SystemExit(1)
    except (InstallError, ReleaseError, preview_backup.BackupError) as exc:
        parser.exit(1, f"Preview operation stopped: {exc}\n")
    except OSError:
        parser.exit(1, "Preview operation stopped: local storage or process operation failed; check permissions and available space\n")


if __name__ == "__main__":
    main()
