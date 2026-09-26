# Developer preview install manager

The developer preview release manager is available as `tools/preview_install.py` on this development branch. This is an unprivileged local development workflow for a disposable preview. It does not install or configure a Raspberry Pi appliance.

Run these commands from an Alltron checkout with Python 3.11 or newer. The examples use `/tmp/alltron-preview` on Linux (its parent `/tmp` already exists) and `C:\AlltronPreview` on Windows. Choose an absolute path whose parent directory exists. The root may be missing or empty for initialization. On Linux, an existing folder must be owned by the current user with mode 0700. Do not use sudo.

## Check prerequisites

```sh
python -m tools.preview_install preflight --root /tmp/alltron-preview
```

PowerShell:

```powershell
python -m tools.preview_install preflight --root C:\AlltronPreview
```

Preflight is read-only and reports machine-readable JSON codes with remedies. It checks Python version, supported desktop OS, at least 64 MiB of free disk space, root path, write access and POSIX privacy permissions, and reports a warning if IANA time-zone data is unavailable. Windows folder ACLs are not audited; use fictional data on a trusted single-user desktop for this preview. Hardware status is preview-only; passing preflight does not certify any device.

## Initialize the managed root

```sh
python -m tools.preview_install init --root /tmp/alltron-preview
```

PowerShell:

```powershell
python -m tools.preview_install init --root C:\AlltronPreview
```

Initialization creates the private managed folder layout under the selected root. It is intended for a missing or empty root; keep application data and the managed root private to the local user.

## Install a source archive

First obtain an archive and its SHA-256 from a source you trust. The startup check executes the candidate's Python code locally, so a checksum from an untrusted source is insufficient. Supply the expected 64-character lowercase hexadecimal digest explicitly:

```sh
python -m tools.preview_install install --root /tmp/alltron-preview --archive /path/to/alltron-source.zip --sha256 EXPECTED_64_HEX
```

PowerShell:

```powershell
python -m tools.preview_install install --root C:\AlltronPreview --archive C:\path\to\alltron-source.zip --sha256 EXPECTED_64_HEX
```

The manager compares the archive with the supplied digest, then validates the strict release manifest and inventory. It stages the candidate, checks Python syntax, and runs a disposable loopback HTTP smoke check using disposable data. Only after those steps pass does it atomically select the candidate as current. A failed candidate leaves the previously selected version in place.

The digest check establishes that the archive matches the value you supplied; it does not prove who produced the archive. Obtain the digest through a trusted source. The source archive format and release review remain governed by [Source preview archive](RELEASE_BUILD.md).

## Check, run, and roll back

```sh
python -m tools.preview_install status --root /tmp/alltron-preview
python -m tools.preview_install run --root /tmp/alltron-preview --port 8765
python -m tools.preview_install rollback --root /tmp/alltron-preview
```

PowerShell:

```powershell
python -m tools.preview_install status --root C:\AlltronPreview
python -m tools.preview_install run --root C:\AlltronPreview --port 8765
python -m tools.preview_install rollback --root C:\AlltronPreview
```

The managed run serves the preview on loopback. It disables Home Assistant, audio, and Codex regardless of ambient `ALLTRON` environment variables. Stop it with Ctrl+C. An exclusive process lock prevents install or rollback while a managed run is active. Atomic current/previous pointers support code rollback and retry after interrupted staging. The manager does not automatically remove old staging directories or prune releases.

Application state is stored separately under `<root>/data`; the install smoke check uses disposable data. Updates and code rollback preserve an existing database before switching code. Rollback selects earlier code only. Use the separate [backup and restore commands](PREVIEW_BACKUP.md) to restore a validated snapshot for the selected release. Schema migrations are future work.

## Scope and limitations

This is local developer tooling. It does not install a service, kiosk, Home Assistant, Python, or appliance dependencies, and it does not establish Raspberry Pi or other hardware acceptance. Uninstall and backups of Home Assistant or account data remain future work. Follow the existing [installation status and contributor setup](INSTALL.md) for the current preview's broader limitations.

Interrupted staging may leave an inactive directory; repeating install verifies and reuses a fully staged release before switching the pointer. Power-loss durability and unattended service recovery remain acceptance work. This document does not announce a main-branch merge or public release.
