"""Inspect local repository files, including ignored files, without following links.

Reports categories and counts only; external auth caches are not audit inputs.
This complements Git history review and archive verification, not a guarantee.
"""

from __future__ import annotations

import argparse
import os
import stat
import zipfile
import io
from pathlib import Path

from tools.publication_audit import CONTENT_RULES, MAX_TEXT_BYTES

FORBIDDEN_NAMES = {".codex", "auth.json", ".env", "secrets", "private",
                   "credentials.json", "config.private.json"}
FORBIDDEN_SUFFIXES = {".token", ".key", ".pem", ".p12", ".pfx"}


def sensitive_name(name: str) -> bool:
    name = name.casefold()
    return (name in FORBIDDEN_NAMES or name.startswith(".env.") or
            Path(name).suffix in FORBIDDEN_SUFFIXES)


def audit_local(root: Path) -> tuple[list[str], int]:
    problems = []
    count = 0

    def content(data: bytes) -> None:
        if any(pattern.search(data) for _, pattern in CONTENT_RULES):
            problems.append("Possible private data in local text")
        # Common auth JSON field names and bearer/JWT/API-key shapes. Fixtures
        # and documentation can produce candidates; inspect locally, never dump.
        import re
        if re.search(rb'"(?:access_token|refresh_token|id_token|OPENAI_API_KEY)"\s*:\s*"[^"\s]+"|\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}|\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', data):
            problems.append("Possible authentication material in local text")

    def walk(folder: Path, directory_fd: int | None = None) -> None:
        nonlocal count
        with os.scandir(directory_fd if directory_fd is not None else folder) as entries:
            for entry in entries:
                # Git objects are reviewed separately. Worktree .git pointers
                # are ordinary Git infrastructure, not runtime credential links.
                if entry.name == ".git":
                    continue
                # Windows DirEntry metadata can omit the hardlink count.
                path = folder / entry.name
                info = (os.stat(entry.name, dir_fd=directory_fd, follow_symlinks=False)
                        if directory_fd is not None else path.lstat())
                if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                    problems.append("Local link or reparse point requires review")
                    continue
                if sensitive_name(entry.name):
                    problems.append("Credential/profile/private path present in repository")
                    continue
                if stat.S_ISDIR(info.st_mode):
                    if directory_fd is not None:
                        child_fd = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                           dir_fd=directory_fd)
                        try:
                            opened = os.fstat(child_fd)
                            if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino) or opened.st_dev != root_info.st_dev:
                                raise ValueError("Directory identity or filesystem changed")
                            walk(path, child_fd)
                        finally:
                            os.close(child_fd)
                    else:
                        # Windows is a static local inventory, not an OS boundary.
                        # Revalidate all ancestors before opening any file below.
                        walk(path)
                    continue
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    problems.append("Local nonregular or hardlinked file requires review")
                    continue
                count += 1
                for ancestor in (folder, *folder.parents):
                    ancestor_info = ancestor.lstat()
                    if stat.S_ISLNK(ancestor_info.st_mode) or getattr(ancestor_info, "st_file_attributes", 0) & 0x400:
                        raise ValueError("Directory became a link")
                descriptor = os.open(entry.name if directory_fd is not None else path,
                                     os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0),
                                     **({"dir_fd": directory_fd} if directory_fd is not None else {}))
                with os.fdopen(descriptor, "rb") as stream:
                    opened = os.fstat(stream.fileno())
                    if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino) or not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
                        raise ValueError("File identity changed")
                    bound = 32 * 1024 * 1024 if path.suffix.casefold() == ".zip" else MAX_TEXT_BYTES
                    data = stream.read(bound + 1)
                if len(data) > bound:
                    problems.append("Oversized local file requires separate review")
                    continue
                if path.suffix.casefold() == ".zip":
                    try:
                        with zipfile.ZipFile(io.BytesIO(data)) as archive:
                            members = archive.infolist()
                            if len(members) > 100 or sum(item.file_size for item in members) > 32 * 1024 * 1024:
                                raise ValueError
                            for item in members:
                                if any(sensitive_name(part) for part in Path(item.filename).parts):
                                    problems.append("Credential/private member in local archive")
                                if item.file_size > MAX_TEXT_BYTES:
                                    raise ValueError
                                content(archive.read(item))
                    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError):
                        problems.append("Local archive could not be fully inspected")
                else:
                    if b"\0" not in data:
                        content(data)

    root = root.absolute()
    for ancestor in (root, *root.parents):
        info = ancestor.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            return ["Audit root cannot contain links"], 0
    root_info = root.lstat()
    if not stat.S_ISDIR(root_info.st_mode) or getattr(root_info, "st_file_attributes", 0) & 0x400:
        return ["Audit root must be a real directory"], 0
    if os.name == "posix":
        # Linux bind mounts can have the same device number. Refuse any mount
        # at/below the root as well as cross-device traversal; never inspect it.
        mounts = Path("/proc/self/mountinfo")
        if not mounts.is_file():
            return ["Mount inventory unavailable on this audit platform"], 0
        for row in mounts.read_text(encoding="utf-8").splitlines():
            import re
            mount = Path(re.sub(r"\\([0-7]{3})", lambda match: chr(int(match[1], 8)), row.split()[4]))
            if mount == root or root in mount.parents:
                return ["Filesystem mount at or below audit root requires separate review"], 0
        descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            opened = os.fstat(descriptor)
            if (opened.st_dev, opened.st_ino) != (root_info.st_dev, root_info.st_ino):
                raise ValueError("Audit root identity changed")
            walk(root, descriptor)
        finally:
            os.close(descriptor)
    else:
        walk(root)
    return problems, count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).absolute().parents[1])
    args = parser.parse_args()
    try:
        problems, count = audit_local(args.repo)
    except (OSError, ValueError):
        print("FAIL: local inventory could not be fully inspected")
        return 1
    for category in sorted(set(problems)):
        print(f"FAIL: {category}")
    if problems:
        print(f"{len(problems)} candidates; inspect locally without printing sensitive values.")
        return 1
    print(f"PASS: {count} local files checked, including ignored files and archive members")
    print("Git objects, credential stores and production isolation require separate review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
