# Source preview archive

This is a Stage 3 software deliverable, not an appliance installer or a Pi release. It packages only committed files named in [RELEASE_PATHS.txt](RELEASE_PATHS.txt). The builder reads Git blobs from `HEAD`, so ignored files and local household data cannot enter the archive through a directory walk. It refuses a dirty worktree, missing files, and symlinks. Each archive includes `RELEASE-MANIFEST.json` with the exact commit, project version, file sizes and SHA-256 hashes. Output goes to ignored `dist/` by default; no archive is published automatically.

From a clean Alltron checkout:

```sh
python tools/build_release.py --output-dir dist
python tools/build_release.py --verify dist/alltron-<version>-<commit12>-source.zip
```

The filename shown by the first command supplies the concrete version and commit. Compare the printed archive SHA-256 with the value from the same trusted build or distribution channel. The manifest checks archive integrity; it does not establish provenance or license approval by itself. Before a public release, review the exact allowlist, complete Git history and every third-party dependency/asset under [the publication gate](PUBLICATION_GATE.md). This archive contains application source and the [local preview manager](PREVIEW_INSTALL.md), which supports code staging, rollback and [local database recovery](PREVIEW_BACKUP.md). It does not include Home Assistant, Codex CLI, Whisper/Piper binaries or models, account state, secrets, runtime backup files, a service installer or hardware support claim.

Next Stage 3 work extends the unprivileged preview rehearsal into a narrowly privileged service/HA installer, account/HA recovery and guided setup on disposable Linux. No command here targets a Raspberry Pi or changes the current household setup.
