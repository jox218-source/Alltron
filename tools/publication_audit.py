"""Fail-closed privacy check for an Alltron branch before public push.

This check supplements, and never replaces, human review of the exact commit SHA.
The original public root commit is the documented legacy metadata exception.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import tempfile
from pathlib import Path


LEGACY_PUBLIC_BASE = "".join(("b400f035", "ea3d6925", "4d71bec5", "ced2a2fe", "1cdd4557"))
EXPECTED_REMOTES = {
    "https://github.com/jox218-source/Alltron",
    "git" + "@" + "github.com:jox218-source/Alltron",
}
OWNER_NAME = "jox218-source"
OWNER_EMAIL = "263269147+jox218-source" + "@" + "users.noreply.github.com"
MAX_TEXT_BYTES = 256 * 1024

# Only report rule names and paths. Never print the matched content to a CI log.
CONTENT_RULES = (
    ("email address", re.compile(rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("private network address", re.compile(rb"\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})\b")),
    ("local home path", re.compile(rb"(?:[A-Za-z]:\\" + b"Users\\\\|/" + b"home/|/" + b"Users/)")),
    ("private key marker", re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)


class AuditError(Exception):
    pass


def git(repo: Path, *args: str) -> bytes:
    process = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, check=False
    )
    if process.returncode:
        raise AuditError(f"git {' '.join(args[:2])} failed; check repository and base revision")
    return process.stdout


def allowed_paths(repo: Path) -> set[str]:
    manifest_path = repo / "docs" / "PUBLIC_PATHS.txt"
    if not manifest_path.is_file():
        raise AuditError("Missing docs/PUBLIC_PATHS.txt")
    paths = [line.strip() for line in manifest_path.read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    if len(paths) != len(set(paths)) or any(
        path.startswith("/") or "\\" in path or path.startswith("../") or "/../" in path
        or "*" in path or "?" in path for path in paths
    ):
        raise AuditError("Public path manifest must contain unique, literal repository-relative paths")
    return set(paths)


def scan_text(data: bytes, location: str) -> list[str]:
    problems = []
    if len(data) > MAX_TEXT_BYTES:
        problems.append(f"{location}: file exceeds {MAX_TEXT_BYTES} bytes")
        return problems
    if b"\0" in data:
        problems.append(f"{location}: binary content")
        return problems
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        problems.append(f"{location}: content is not UTF-8 text")
        return problems
    for name, pattern in CONTENT_RULES:
        if pattern.search(data):
            problems.append(f"{location}: possible {name}")
    return problems


def valid_identity(name: str, email: str) -> bool:
    if name == OWNER_NAME:
        return email == OWNER_EMAIL
    return email.endswith("@users.noreply.github.com") or (name == "GitHub" and email == "noreply" + "@" + "github.com")


def audit_history(repo: Path, base: str, head: str, manifest: set[str], *, run_scanner: bool) -> tuple[list[str], int, int]:
    problems: list[str] = []
    commits = git(repo, "rev-list", "--reverse", f"{base}..{head}").decode().splitlines()
    if not commits:
        problems.append("No commits beyond the legacy public base to audit")
    seen_blobs: set[str] = set()
    historical_blobs: list[tuple[str, str, bytes]] = []
    for commit in commits:
        fields = git(repo, "show", "-s", "--format=%an%x00%ae%x00%cn%x00%ce%x00%B", commit).decode("utf-8").split("\0", 4)
        if len(fields) != 5:
            problems.append(f"{commit[:12]}: unreadable commit metadata")
            continue
        author, author_email, committer, committer_email, message = fields
        if not valid_identity(author, author_email) or not valid_identity(committer, committer_email):
            problems.append(f"{commit[:12]}: author or committer lacks approved no-reply identity")
        problems.extend(scan_text(message.encode("utf-8"), f"{commit[:12]} message"))
        entries = git(repo, "ls-tree", "-r", "-z", commit).split(b"\0")
        for entry in entries:
            if not entry:
                continue
            metadata, raw_path = entry.split(b"\t", 1)
            mode, kind, raw_oid = metadata.decode("ascii").split(" ")
            path = raw_path.decode("utf-8")
            if path not in manifest:
                problems.append(f"{commit[:12]}: unapproved path {path}")
            if kind != "blob" or mode not in ("100644", "100755"):
                problems.append(f"{commit[:12]}: prohibited file type at {path}")
                continue
            oid = raw_oid
            if oid in seen_blobs:
                continue
            seen_blobs.add(oid)
            content = git(repo, "cat-file", "blob", oid)
            problems.extend(scan_text(content, f"{commit[:12]}:{path}"))
            historical_blobs.append((oid, path, content))
    if run_scanner:
        problems.extend(scan_historical_blobs(historical_blobs))
    return problems, len(commits), len(seen_blobs)


def scan_historical_blobs(blobs: list[tuple[str, str, bytes]]) -> list[str]:
    if not blobs:
        return []
    try:
        from detect_secrets.core.scan import scan_file
        from detect_secrets.settings import default_settings
    except ImportError:
        return ["detect-secrets is unavailable; install the audit extra and retry"]
    problems: list[str] = []
    with tempfile.TemporaryDirectory(prefix="alltron-audit-") as directory:
        with default_settings() as settings:
            # Never send candidate values to online verification services.
            settings.disable_filters("detect_secrets.filters.common.is_ignored_due_to_verification_policies")
            for oid, original_path, content in blobs:
                if b"\0" in content or len(content) > MAX_TEXT_BYTES:
                    continue  # scan_text already rejects binary and oversized blobs.
                temporary = Path(directory) / (oid + ".txt")
                descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(descriptor, "wb") as file:
                    file.write(content)
                try:
                    for finding in scan_file(str(temporary)):
                        problems.append(f"detect-secrets flagged historical blob {original_path}:{finding.line_number}")
                finally:
                    temporary.unlink()
    return problems


def audit(repo: Path, base: str, head: str, *, run_scanner: bool = True) -> tuple[list[str], int, int]:
    repo = repo.resolve()
    problems: list[str] = []
    if git(repo, "status", "--porcelain", "--untracked-files=all").strip():
        problems.append("Working tree is not clean; commit or remove local changes before audit")
    remote = git(repo, "remote", "get-url", "origin").decode().strip().removesuffix(".git")
    if remote not in EXPECTED_REMOTES:
        problems.append("origin does not point to the expected public Alltron repository")
    resolved_head = git(repo, "rev-parse", head).decode().strip()
    resolved_base = git(repo, "rev-parse", base).decode().strip()
    if resolved_base != LEGACY_PUBLIC_BASE:
        problems.append("Audit base is not the documented original public commit")
    ancestor = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", resolved_base, resolved_head],
        capture_output=True, check=False,
    )
    if ancestor.returncode:
        problems.append("Original public commit is not an ancestor of the proposed head")
        return problems, 0, 0
    manifest = allowed_paths(repo)
    if "docs/PUBLIC_PATHS.txt" not in manifest:
        problems.append("Manifest must include itself")
    history_problems, commit_count, blob_count = audit_history(
        repo, resolved_base, resolved_head, manifest, run_scanner=run_scanner
    )
    problems.extend(history_problems)
    return problems, commit_count, blob_count


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit every post-root Alltron commit before publication")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--base", default=LEGACY_PUBLIC_BASE)
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args()
    try:
        problems, commits, blobs = audit(args.repo, args.base, args.head)
    except AuditError as error:
        print(f"FAIL: {error}")
        return 1
    for problem in problems:
        print(f"FAIL: {problem}")
    if problems:
        return 1
    print(f"PASS: audited {commits} post-root commits and {blobs} historical text blobs")
    print("Manual Sol High review of the exact head SHA and release archive is still required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
