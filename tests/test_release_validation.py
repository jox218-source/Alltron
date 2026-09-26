import hashlib
import io
import json
import stat
import unittest
import zipfile

from tools.build_release import MANIFEST, ReleaseError, verified_payloads, zip_entry


def archive_bytes(extra=None, change_manifest=None, change_info=None):
    payloads = {"README.md": b"Fictional preview\n", "pyproject.toml": b'[project]\nversion = "0.1.0a0"\n'}
    payloads.update(extra or {})
    payloads["docs/RELEASE_PATHS.txt"] = ("\n".join(sorted([*payloads, "docs/RELEASE_PATHS.txt"])) + "\n").encode()
    manifest = {"schema": 1, "kind": "source-preview", "version": "0.1.0a0", "commit": "a" * 40,
                "files": [{"path": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                          for name, data in sorted(payloads.items())]}
    if change_manifest:
        change_manifest(manifest)
    payloads[MANIFEST] = json.dumps(manifest).encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in payloads.items():
            info, data = zip_entry(name, data)
            if change_info:
                change_info(info)
            archive.writestr(info, data)
    return buffer.getvalue()


class ReleaseValidationTests(unittest.TestCase):
    def test_directory_prefix_case_aliases_are_rejected(self):
        with self.assertRaisesRegex(ReleaseError, "capitalization"):
            verified_payloads(archive_bytes({"Folder/a.py": b"fixture", "folder/b.py": b"fixture"}))

    def test_portable_paths_cannot_escape_or_alias(self):
        for path in ("../escape.py", "/absolute.py", "folder/../escape.py", "C:/escape.py", "NUL.txt",
                     "folder./file.py", "folder\\file.py", "readme.md", "folder", "folder/file.py/child"):
            extra = {path: b"fixture"}
            if path in ("folder", "folder/file.py/child"):
                extra["folder/file.py"] = b"fixture"
            with self.subTest(path=path), self.assertRaises(ReleaseError):
                verified_payloads(archive_bytes(extra))

    def test_symlink_metadata_rejected_before_extraction(self):
        def link(info):
            if info.filename == "README.md":
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
        with self.assertRaisesRegex(ReleaseError, "unsupported entry"):
            verified_payloads(archive_bytes(change_info=link))

    def test_manifest_types_and_identity_are_strict(self):
        changes = [lambda manifest: manifest.update(schema=True),
                   lambda manifest: manifest.update(commit="../pointer"),
                   lambda manifest: manifest.update(version="different-version"),
                   lambda manifest: manifest["files"][0].update(size=True),
                   lambda manifest: manifest["files"][0].update(sha256="invalid"),
                   lambda manifest: manifest["files"].pop()]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ReleaseError):
                verified_payloads(archive_bytes(change_manifest=change))

    def test_source_allowlist_must_match_every_entry(self):
        data = archive_bytes()
        buffer = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(data)) as original, zipfile.ZipFile(buffer, "w") as altered:
            contents = {name: original.read(name) for name in original.namelist()}
            contents["docs/RELEASE_PATHS.txt"] = b"pyproject.toml\ndocs/RELEASE_PATHS.txt\n"
            manifest = json.loads(contents[MANIFEST])
            for entry in manifest["files"]:
                payload = contents[entry["path"]]
                entry.update(size=len(payload), sha256=hashlib.sha256(payload).hexdigest())
            contents[MANIFEST] = json.dumps(manifest).encode()
            for name, payload in contents.items():
                altered.writestr(name, payload)
        with self.assertRaisesRegex(ReleaseError, "source allowlist"):
            verified_payloads(buffer.getvalue())

    def test_immutable_snapshot_is_verified_without_extraction(self):
        manifest, payloads = verified_payloads(archive_bytes())
        self.assertEqual(manifest["version"], "0.1.0a0")
        self.assertEqual(payloads["README.md"], b"Fictional preview\n")


if __name__ == "__main__":
    unittest.main()
