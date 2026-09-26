"""Build and verify a deterministic source preview from reviewed Git blobs.

This creates a source archive only. It never installs software or bundles owner
state, credentials, model weights, audio, or third-party binaries.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import stat
import tempfile
import tomllib
import zipfile
from pathlib import Path, PurePosixPath


MANIFEST = "RELEASE-MANIFEST.json"
FIXED_TIME = (1980, 1, 1, 0, 0, 0)
MAX_FILE_BYTES = 256 * 1024
MAX_MANIFEST_BYTES = 256 * 1024
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024


class ReleaseError(Exception):
    pass


def git(repo: Path, *args: str) -> bytes:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    if result.returncode:
        raise ReleaseError("Git source check failed") from None
    return result.stdout


def release_paths(data: bytes) -> list[str]:
    paths = []
    for raw in data.decode("utf-8").splitlines():
        path = raw.strip()
        if not path or path.startswith("#"):
            continue
        part = PurePosixPath(path)
        if (part.is_absolute() or "\\" in path or ".." in part.parts or
                path != part.as_posix() or path.startswith("-") or
                not re.fullmatch(r"[A-Za-z0-9_./-]+", path)):
            raise ReleaseError("Invalid release path")
        for component in part.parts:
            if component.endswith(".") or re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])", component.split(".")[0], re.I):
                raise ReleaseError("Nonportable release path")
        paths.append(path)
    if not paths or len(paths) != len({path.casefold() for path in paths}) or MANIFEST.casefold() in {path.casefold() for path in paths}:
        raise ReleaseError("Release path list is empty or duplicated")
    prefixes = {}
    for path in paths:
        components = PurePosixPath(path).parts
        for length in range(1, len(components) + 1):
            prefix = "/".join(components[:length])
            key = prefix.casefold()
            if key in prefixes and prefixes[key] != prefix:
                raise ReleaseError("Release paths have conflicting capitalization")
            prefixes[key] = prefix
    return sorted(paths)


def committed_files(repo: Path) -> dict[str, tuple[str, str]]:
    files = {}
    for row in git(repo, "ls-tree", "-rz", "HEAD").split(b"\0"):
        if not row:
            continue
        metadata, name = row.split(b"\t", 1)
        mode, kind, oid = metadata.decode("ascii").split()
        files[name.decode("utf-8")] = (mode, oid) if kind == "blob" else (kind, oid)
    return files


def zip_entry(name: str, payload: bytes) -> tuple[zipfile.ZipInfo, bytes]:
    info = zipfile.ZipInfo(name, FIXED_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    info.create_system = 3
    return info, payload


def build_release(repo: Path, output_dir: Path) -> Path:
    repo = repo.resolve()
    if git(repo, "status", "--porcelain", "--untracked-files=all").strip():
        raise ReleaseError("Commit or remove worktree changes before building")
    commit = git(repo, "rev-parse", "HEAD").decode("ascii").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ReleaseError("Invalid commit identity")
    tree = committed_files(repo)
    allowlist = "docs/RELEASE_PATHS.txt"
    if allowlist not in tree or tree[allowlist][0] != "100644":
        raise ReleaseError("Release allowlist must be a regular committed file")
    paths = release_paths(git(repo, "cat-file", "blob", tree[allowlist][1]))
    if allowlist not in paths or "pyproject.toml" not in paths:
        raise ReleaseError("Release metadata files must be included")

    payloads = {}
    for path in paths:
        if path not in tree or tree[path][0] not in ("100644", "100755"):
            raise ReleaseError(f"Missing or nonregular release file: {path}")
        payload = git(repo, "cat-file", "blob", tree[path][1])
        if len(payload) > MAX_FILE_BYTES:
            raise ReleaseError(f"Release file is too large: {path}")
        payloads[path] = payload

    version = tomllib.loads(payloads["pyproject.toml"].decode("utf-8"))["project"]["version"]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", version):
        raise ReleaseError("Invalid release version")
    manifest = {
        "schema": 1,
        "kind": "source-preview",
        "version": version,
        "commit": commit,
        "files": [
            {"path": path, "sha256": hashlib.sha256(payloads[path]).hexdigest(), "size": len(payloads[path])}
            for path in paths
        ],
    }
    payloads[MANIFEST] = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"alltron-{version}-{commit[:12]}-source.zip"
    with tempfile.NamedTemporaryFile(dir=output_dir, suffix=".tmp", delete=False) as temporary:
        pending = Path(temporary.name)
    try:
        with zipfile.ZipFile(pending, "w") as archive:
            for path in sorted(payloads):
                info, payload = zip_entry(path, payloads[path])
                archive.writestr(info, payload)
        verify_release(pending)
        os.replace(pending, target)
    finally:
        pending.unlink(missing_ok=True)
    return target


def read_archive_bytes(archive_path: Path) -> bytes:
    with archive_path.open("rb") as stream:
        data = stream.read(MAX_ARCHIVE_BYTES + 1)
    if len(data) > MAX_ARCHIVE_BYTES:
        raise ReleaseError("Archive exceeds size limit")
    return data


def verified_payloads(data: bytes) -> tuple[dict, dict[str, bytes]]:
    """Validate a bounded immutable snapshot before any extraction or execution."""
    try:
        if len(data) > MAX_ARCHIVE_BYTES:
            raise ReleaseError("Archive exceeds size limit")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len({name.casefold() for name in names}) or names.count(MANIFEST) != 1:
                raise ReleaseError("Archive has duplicate or missing entries")
            if len(infos) > 100 or archive.getinfo(MANIFEST).file_size > MAX_MANIFEST_BYTES:
                raise ReleaseError("Archive inventory exceeds limits")
            if any(info.file_size > MAX_FILE_BYTES for info in infos if info.filename != MANIFEST):
                raise ReleaseError("Archive file exceeds limit")
            for info in infos:
                if (info.is_dir() or stat.S_IFMT(info.external_attr >> 16) not in (0, stat.S_IFREG)
                        or info.flag_bits & 1 or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
                    raise ReleaseError("Archive contains an unsupported entry")
            manifest = json.loads(archive.read(MANIFEST))
            if not isinstance(manifest, dict) or set(manifest) != {"schema", "kind", "version", "commit", "files"}:
                raise ReleaseError("Invalid archive manifest")
            if (type(manifest["schema"]) is not int or manifest["schema"] != 1 or manifest["kind"] != "source-preview"
                    or not isinstance(manifest["commit"], str) or not re.fullmatch(r"[0-9a-f]{40}", manifest["commit"])
                    or not isinstance(manifest["version"], str)
                    or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", manifest["version"])):
                raise ReleaseError("Unsupported archive identity")
            entries = manifest["files"]
            if not isinstance(entries, list):
                raise ReleaseError("Invalid archive manifest inventory")
            for entry in entries:
                if (not isinstance(entry, dict) or set(entry) != {"path", "sha256", "size"}
                        or not isinstance(entry["path"], str) or type(entry["size"]) is not int
                        or not 0 <= entry["size"] <= MAX_FILE_BYTES or not isinstance(entry["sha256"], str)
                        or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])):
                    raise ReleaseError("Invalid archive file record")
            expected = [entry["path"] for entry in entries] + [MANIFEST]
            if sorted(names) != sorted(expected) or len(expected) != len(set(expected)):
                raise ReleaseError("Archive inventory does not match manifest")
            payloads = {MANIFEST: archive.read(MANIFEST)}
            for entry in entries:
                if release_paths(entry["path"].encode("utf-8")) != [entry["path"]]:
                    raise ReleaseError("Invalid archive path")
                if any(str(parent).casefold() in {name.casefold() for name in names}
                       for parent in PurePosixPath(entry["path"]).parents if str(parent) != "."):
                    raise ReleaseError("Archive path conflicts with a directory")
                payload = archive.read(entry["path"])
                if len(payload) != entry["size"] or hashlib.sha256(payload).hexdigest() != entry["sha256"]:
                    raise ReleaseError("Archive file hash mismatch")
                payloads[entry["path"]] = payload
            allowed = release_paths(payloads["docs/RELEASE_PATHS.txt"])
            if allowed != sorted(entry["path"] for entry in entries):
                raise ReleaseError("Archive inventory does not match source allowlist")
            project = tomllib.loads(payloads["pyproject.toml"].decode("utf-8"))["project"]
            if project["version"] != manifest["version"]:
                raise ReleaseError("Archive version does not match project")
            return manifest, payloads
    except (OSError, zipfile.BadZipFile, KeyError, TypeError, ValueError, RuntimeError, NotImplementedError) as exc:
        raise ReleaseError("Invalid release archive") from exc


def verify_release(archive_path: Path) -> dict:
    return verified_payloads(read_archive_bytes(archive_path))[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("dist"))
    parser.add_argument("--verify", type=Path, help="verify an existing source archive")
    args = parser.parse_args()
    try:
        if args.verify:
            manifest = verify_release(args.verify)
            print(f"Verified source preview {manifest['version']} at {manifest['commit'][:12]}")
        else:
            target = build_release(Path(__file__).resolve().parents[1], args.output_dir)
            print(f"Built {target} (SHA-256 {hashlib.sha256(target.read_bytes()).hexdigest()})")
    except ReleaseError as exc:
        parser.exit(1, f"Release build failed: {exc}\n")


if __name__ == "__main__":
    main()
