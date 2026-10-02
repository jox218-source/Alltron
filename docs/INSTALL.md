# Installation

## Current status

**Alltron is pre-alpha.** The Linux owner mode and Home Assistant OAuth setup UI are implemented, but live Home Assistant authorization, service deployment, speech, and hardware acceptance remain open. The Linux service CLI prepares and installs user units, but activation is deliberately refused pending acceptance. Codex answers are hard-disabled. This is not a Pi appliance installer; do not install it on a production household Pi. See [owner setup](OWNER_SETUP.md), [Linux services](LINUX_SERVICES.md), [speech development](VOICE_DEVELOPMENT.md), and [Stage 2 development](STAGE2_DEVELOPMENT.md).

An unqualified `python -m alltron` launch now exits with an error. Choose one of the two explicit paths below: Linux owner mode with a private owner profile and HTTPS, or the disconnected fictional fixture preview. Do not use fixture mode with household data or credentials.

## Linux owner quickstart

Use this owner quickstart only in a disposable Linux environment while Alltron remains pre-alpha. Python 3.11 or newer and OpenSSL are required. Run as an ordinary Linux user, without `sudo`. Choose a dedicated absolute profile outside the repository and any shared or synchronized directory:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
python -m alltron.setup --profile /absolute/private/alltron-profile
alltron --owner-profile /absolute/private/alltron-profile/owner.json
```

The setup command prompts twice for a local Alltron password without echoing it. It creates the owner profile and HTTPS certificate. Open the exact `https://127.0.0.1:<port>` address printed by Alltron on the same device. Before entering the password in the browser, compare the browser certificate's SHA-256 fingerprint with:

```sh
openssl x509 -in /absolute/private/alltron-profile/alltron.crt -noout -fingerprint -sha256
```

Trust only this generated certificate after the fingerprints match exactly. Stop if they differ or the browser cannot verify the expected identity. The browser uses the local Alltron password only to unlock the local service. Home Assistant OAuth access and refresh credentials stay server-side in the private owner profile; the UI never asks for a Home Assistant password or token. In the Connections panel, the owner can start Home Assistant authorization, select listed entities, assign names, and request revocation. Live authorization remains unaccepted; see [OWNER_SETUP.md](OWNER_SETUP.md) for TLS prerequisites and revocation behavior. Codex answers are hard-disabled.

Linux service preparation uses the exact managed source archive and requires rootless Podman and systemd user services. The installer can prepare and install private user units but activation is currently refused pending disposable Linux acceptance. See [LINUX_SERVICES.md](LINUX_SERVICES.md). Do not enable or start the units manually.

## Disconnected fictional fixture preview

This explicit cross-platform preview uses an isolated temporary data directory outside the Git checkout. It is disconnected from Home Assistant and Codex and must use fictional data only.

Linux/macOS:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
mkdir -p /tmp/alltron-fixture-data
ALLTRON_DATA_DIR=/tmp/alltron-fixture-data python -m alltron --fixture-preview
```

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -e .
$env:ALLTRON_DATA_DIR = Join-Path $env:TEMP 'alltron-fixture-data'
New-Item -ItemType Directory -Force -Path $env:ALLTRON_DATA_DIR | Out-Null
& .\.venv\Scripts\python.exe -m alltron --fixture-preview
```

Open **http://127.0.0.1:8765** on the same computer. Fixture mode does not use owner login, Home Assistant, Codex, or live speech engines. Do not supply real credentials or household data. Stop the process with Ctrl+C. The fixture data directory is separate from the repository and from the production owner profile.

## For contributors

You can review the design and propose changes through GitHub. The package currently has no third-party runtime dependencies. Python 3.11 or newer and pip are required to create the local environment and install the preview.

## Versioned developer preview

The [preview release manager](PREVIEW_INSTALL.md) checks prerequisites, stages a checksum-verified source archive in a private local folder, tests it with disposable data, and offers managed startup and code rollback. Use this to rehearse software updates on a computer. Its [backup and restore commands](PREVIEW_BACKUP.md) preserve local timer, alarm and shopping state, with a safety copy before replacement. It does not install Home Assistant, configure services/kiosk/audio, back up accounts or HA data, or establish Pi support. Keep the trusted archive checksum available and stop the managed preview before updating it.

## Before a future install

When installation becomes available, use only a tagged release and the commands published on that release's page. Read the release's hardware support list, privacy notes, upgrade instructions, and rollback steps first. Never paste Home Assistant tokens, Codex credentials, or diagnostic bundles into a public issue.
