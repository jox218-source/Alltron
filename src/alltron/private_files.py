"""Bounded owner-only files outside source repositories; never report their contents."""

from __future__ import annotations

import os
import stat
from pathlib import Path


def checked_path(path: Path, *, directory: bool = False) -> Path:
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("Private paths must be absolute and contain no traversal")
    for component in (*reversed(path.parents), path):
        info = component.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Private paths cannot contain links or reparse points")
        if component.is_dir() and (component / ".git").exists():
            raise ValueError("Private paths must be outside source repositories")
    info = path.lstat()
    if directory:
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError("Private directory is unavailable")
    elif not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("Private file must be a regular file with one link")
    return path


def _owner_only(info: os.stat_result, *, directory: bool = False) -> None:
    if os.name == "posix" and (info.st_uid != os.geteuid() or info.st_mode & 0o077):
        raise ValueError("Private files and their parent directory must be owner-only")
    if not directory and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
        raise ValueError("Private file must be a regular file with one link")


def read_private_text(path: Path, limit: int) -> str:
    """POSIX walks via no-follow directory descriptors, including the final open.

    Windows validates links before/after opening but is not the appliance security
    boundary: Windows owner ACL enforcement remains a separate acceptance gate.
    """
    path = checked_path(path)
    descriptor = None
    parent = None
    try:
        if os.name == "posix":
            parent = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
            for component in path.parts[1:-1]:
                next_parent = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                      dir_fd=parent)
                os.close(parent)
                parent = next_parent
            _owner_only(os.fstat(parent), directory=True)
            descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                 dir_fd=parent)
        else:
            descriptor = os.open(path, os.O_RDONLY | os.O_BINARY)
        info = os.fstat(descriptor)
        _owner_only(info)
        after = checked_path(path).lstat()
        if (info.st_dev, info.st_ino) != (after.st_dev, after.st_ino) or info.st_size > limit:
            raise ValueError("Private file changed or exceeds its size limit")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise ValueError("Private file exceeds its size limit")
        try:
            return data.decode("utf-8")
        except UnicodeError:
            raise ValueError("Private file must contain UTF-8 text") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if parent is not None:
            os.close(parent)
