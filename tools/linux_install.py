"""Explicit Linux service preparation; uses the reviewed source-archive manager."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import preview_install as manager

HA_IMAGE = "ghcr.io/home-assistant/home-assistant@sha256:3e6710a7ab2a61311d9d899b719f6c3657791c63e8f4942cec4ebc42401d6b76"
UNITS = ("alltron.service", "alltron-ha.service")


def user() -> None:
    if sys.platform != "linux" or os.geteuid() == 0:
        raise ValueError("Use an ordinary Linux user without sudo")


def modules():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from alltron.private_files import checked_path, read_private_text
    from alltron.setup import private_write, certificate
    from alltron.owner import OwnerAuth
    return checked_path, read_private_text, private_write, certificate, OwnerAuth


def safe_path(path: Path) -> Path:
    # systemd specifiers, shell metacharacters, control chars and mount separators
    # are not accepted in installer paths. Commands are never shell evaluated.
    if not path.is_absolute() or any(c in str(path) for c in '%\n\r\t"\\:') or ".." in path.parts:
        raise ValueError("Choose simple absolute Linux paths without unit or mount syntax")
    return path


def quoted(path: Path) -> str:
    return '"' + str(safe_path(path)) + '"'


def preflight() -> dict:
    return {"linux": sys.platform == "linux", "ordinary_user": os.name == "posix" and os.geteuid() != 0,
            "python": sys.version_info >= (3, 11), "openssl": bool(shutil.which("openssl")),
            "podman": bool(shutil.which("podman")), "systemctl": bool(shutil.which("systemctl")),
            "codex_enabled": False, "live_acceptance": False}


def prepare(root: Path, profile: Path, ha_root: Path, *, port: int = 8765, ha_port: int = 8123) -> dict:
    user()
    checked, read, write, certificate, OwnerAuth = modules()
    roots = tuple(safe_path(path) for path in (root, profile, ha_root))
    for i, left in enumerate(roots):
        for right in roots[i + 1:]:
            if left == right or left in right.parents or right in left.parents:
                raise ValueError("Use separate application, owner and HA directories")
    if (isinstance(port, bool) or isinstance(ha_port, bool) or not isinstance(port, int)
            or not isinstance(ha_port, int) or not 1 <= port <= 65535 or not 1 <= ha_port <= 65535 or port == ha_port):
        raise ValueError("Choose different valid loopback ports")
    checked(profile, directory=True)
    checked(root, directory=True)
    OwnerAuth(profile / "owner.json").context()
    openssl, podman = shutil.which("openssl"), shutil.which("podman")
    if not openssl or not podman or not shutil.which("systemctl"):
        raise ValueError("Install OpenSSL, rootless Podman and systemd user services first")
    interpreter = Path("/usr/bin/python3")
    if not interpreter.is_file() or subprocess.run([str(interpreter), "-I", "-c", "import sys;sys.exit(sys.version_info < (3,11))"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5).returncode:
        raise ValueError("Install system Python 3.11 or newer outside user home")
    checked(ha_root.parent, directory=True)
    with manager.locked(root):
        state = manager.load_state(root)
        if not state["current"]:
            raise ValueError("Install a verified source archive first")
        content, manifest = manager.release_on_disk(root, state["current"])
        if not (content / "tools" / "linux_install.py").is_file():
            raise ValueError("This source archive has no reviewed service installer")
        if ha_root.exists():
            checked(ha_root, directory=True)
            info = ha_root.stat()
            if info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise ValueError("HA directory must be private and owned by this user")
        marker = ha_root / "alltron-ha.json"
        if marker.exists():
            data = json.loads(read(marker, 4096))
            if data != {"format": "alltron-ha-1", "image": HA_IMAGE, "port": ha_port}:
                raise ValueError("Existing HA profile differs; do not overwrite its identity")
        else:
            if ha_root.exists() and any(ha_root.iterdir()):
                raise ValueError("Use an empty dedicated HA directory")
            with tempfile.TemporaryDirectory(dir=ha_root.parent, prefix=".alltron-ha-") as temporary:
                pending = Path(temporary) / "profile"
                pending.mkdir(mode=0o700)
                certificate(pending, "ha", openssl)
                write(pending / "configuration.yaml", 'frontend:\nhttp:\n  ssl_certificate: /config/ha.crt\n  ssl_key: /config/ha.key\n  server_port: 8123\n')
                write(pending / marker.name, json.dumps({"format": "alltron-ha-1", "image": HA_IMAGE, "port": ha_port}))
                if ha_root.exists():
                    ha_root.rmdir()
                pending.rename(ha_root)
        # Import only a checked public certificate, never HA's signing key.
        write(profile / "ha-ca.crt", read(ha_root / "ha.crt", 16384))
        write(profile / "ha-endpoint.json", json.dumps({"port": ha_port, "ca_file": str(profile / "ha-ca.crt")}))
        launcher = content / "tools" / "linux_install.py"
        app_command = f'{quoted(interpreter)} -I -B {quoted(launcher)} run --root {quoted(root)} --profile {quoted(profile)} --port {port}'
        ha_command = (f'{quoted(Path(podman))} run --rm --name alltron-ha --pull=never --cap-drop=ALL '
                      f'--security-opt=no-new-privileges --pids-limit=256 --memory=2g '
                      f'--publish=127.0.0.1:{ha_port}:8123 --volume={quoted(ha_root)}:/config:Z {HA_IMAGE}')
        app_unit = f'''[Unit]
Description=Alltron authenticated local assistant
After=alltron-ha.service
[Service]
ExecStart={app_command}
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=tmpfs
BindReadOnlyPaths={quoted(root)}
BindPaths={quoted(root / "data")} {quoted(profile)}
ReadWritePaths={quoted(root / "data")} {quoted(profile)} {quoted(root / ".lock")}
RestrictAddressFamilies=AF_INET
IPAddressDeny=any
IPAddressAllow=127.0.0.1
ProtectProc=invisible
ProcSubset=pid
RestrictSUIDSGID=yes
LockPersonality=yes
MemoryMax=512M
TasksMax=32
[Install]
WantedBy=default.target
'''
        ha_unit = f'''[Unit]
Description=Dedicated Alltron Home Assistant container
[Service]
ExecStart={ha_command}
ExecStop={quoted(Path(podman))} stop --time=20 alltron-ha
Restart=on-failure
RestartSec=10
TimeoutStopSec=30
UMask=0077
[Install]
WantedBy=default.target
'''
        for name, unit in zip(UNITS, (app_unit, ha_unit)):
            write(profile / name, unit)
        write(profile / "services.json", json.dumps({"format": "alltron-services-1", "root": str(root),
                                                     "ha_root": str(ha_root), "archive": state["current"],
                                                     "port": port, "ha_port": ha_port}))
        fingerprints = {name: hashlib.sha256(__import__("ssl").PEM_cert_to_DER_cert(read(profile / name, 16384))).hexdigest()
                        for name in ("alltron.crt", "ha-ca.crt")}
        return {"status": "prepared", "version": manifest["version"], "certificate_sha256": fingerprints,
                "services_started": False, "ha_image": HA_IMAGE, "codex_enabled": False}


def service(profile: Path, action: str) -> dict:
    user()
    checked, read, write, _, OwnerAuth = modules()
    safe_path(profile)
    OwnerAuth(profile / "owner.json").context()
    data = json.loads(read(profile / "services.json", 4096))
    if not isinstance(data, dict) or data.get("format") != "alltron-services-1":
        raise ValueError("Prepare services first")
    destination = Path.home() / ".config" / "systemd" / "user"
    if action == "install-services":
        # The dedicated setup CLI owns service installation, never the web API.
        for ancestor in (Path.home() / ".config", destination.parent, destination):
            if not ancestor.exists():
                ancestor.mkdir(mode=0o700)
            checked(ancestor, directory=True)
        for name in UNITS:
            target = destination / name
            if target.exists():
                existing = read(target, 16384)
                if existing != read(profile / name, 16384):
                    raise ValueError("A different service uses this name; uninstall its reviewed units before reprepare")
        for name in UNITS:
            target = destination / name
            write(target, read(profile / name, 16384))
        commands = [["daemon-reload"]]
    elif action == "activate":
        raise ValueError("Activation remains gated by disposable container and service acceptance; use the documented review procedure")
    elif action == "deactivate":
        for name in UNITS:
            if not (destination / name).exists() or read(destination / name, 16384) != read(profile / name, 16384):
                raise ValueError("Missing or changed service file preserved; review manually")
        commands = [["disable", "--now", *UNITS]]
    elif action == "uninstall-services":
        result = service(profile, "deactivate")
        for name in UNITS:
            target = destination / name
            if target.exists():
                if read(target, 16384) != read(profile / name, 16384):
                    raise ValueError("Changed service file preserved; review manually")
                target.unlink()
        commands = [["daemon-reload"]]
    else:
        raise ValueError("Unknown service action")
    systemctl = shutil.which("systemctl")
    if not systemctl:
        raise ValueError("systemd user services unavailable")
    for command in commands:
        result = subprocess.run([systemctl, "--user", *command], stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=40)
        if result.returncode:
            raise ValueError("User service operation failed; inspect local service status")
    return {"status": action, "data_preserved": True, "codex_enabled": False}


def run(root: Path, profile: Path, port: int) -> None:
    user()
    with manager.locked(root):
        state = manager.load_state(root)
        content, _ = manager.release_on_disk(root, state["current"])
        sys.path.insert(0, str(content / "src"))
        # Only service-owned voice settings may be introduced after audio review.
        for name in tuple(os.environ):
            if name.startswith(("ALLTRON_", "OPENAI_", "CODEX_")):
                del os.environ[name]
        from alltron.server import serve
        serve(port, manager.data_directory(root) / "timers.sqlite3", owner_profile=profile / "owner.json")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("preflight")
    command = commands.add_parser("prepare")
    for name in ("root", "profile", "ha-root"):
        command.add_argument("--" + name, type=Path, required=True)
    command.add_argument("--port", type=int, default=8765)
    command.add_argument("--ha-port", type=int, default=8123)
    command = commands.add_parser("run")
    command.add_argument("--root", type=Path, required=True)
    command.add_argument("--profile", type=Path, required=True)
    command.add_argument("--port", type=int, default=8765)
    for name in ("install-services", "activate", "deactivate", "uninstall-services"):
        commands.add_parser(name).add_argument("--profile", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "preflight":
            result = preflight()
        elif args.command == "prepare":
            result = prepare(args.root, args.profile, args.ha_root, port=args.port, ha_port=args.ha_port)
        elif args.command == "run":
            run(args.root, args.profile, args.port)
            return
        else:
            result = service(args.profile, args.command)
        print(json.dumps(result, sort_keys=True))
    except (OSError, ValueError, manager.InstallError, manager.ReleaseError, subprocess.TimeoutExpired):
        parser.exit(1, "Linux setup stopped: check prerequisites, reviewed archive and private profile. No acceptance is implied.\n")


if __name__ == "__main__":
    main()
