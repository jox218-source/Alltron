# Alltron

**An open-source household assistant being built for a Raspberry Pi.**

Alltron aims to combine local voice, timers, a touchscreen, Home Assistant controls, and optional general answers through each owner's Codex CLI login. The intended appliance installs Home Assistant Container on the same Pi. Owners will bring their own accounts. Personal-file search and the original private household setup are outside this public project.

> **Pre-alpha:** the Linux owner mode and guided Home Assistant OAuth UI are implemented, but live Home Assistant setup, Linux service deployment, speech, and hardware acceptance have not passed. This is not a ready-made Pi appliance. Codex answers are hard-disabled. Read the limits in [owner setup](docs/OWNER_SETUP.md) before using the owner path.

## Linux owner quickstart

Python 3.11 or newer and OpenSSL are required. Run as an ordinary Linux user, without `sudo`. Choose a dedicated absolute profile outside the repository, shared folders, and sync folders:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -m alltron.setup --profile /absolute/private/alltron-profile
alltron --owner-profile /absolute/private/alltron-profile/owner.json
```

The setup CLI prompts for the local Alltron password without echoing it and creates the private owner profile and HTTPS certificate. Open **https://127.0.0.1:8765** on the same device. Before entering the password, compare the browser certificate's SHA-256 fingerprint with the profile certificate:

```sh
openssl x509 -in /absolute/private/alltron-profile/alltron.crt -noout -fingerprint -sha256
```

Trust only the generated certificate after the fingerprints match exactly. Stop if the identity differs or the browser cannot verify it. The owner UI keeps the Alltron password local; Home Assistant OAuth access and refresh credentials stay in the private server-side profile. The Connections panel starts Home Assistant authorization, loads available entities, lets the owner select and name devices, and offers revocation. It does not ask for the Home Assistant password or token. Live authorization remains unaccepted. Codex answers are disabled. See [owner setup](docs/OWNER_SETUP.md) for the full procedure and recovery limits.

## Disconnected fixture preview

For a fictional-data preview on Linux, macOS, or Windows, use a dedicated temporary data directory outside the Git checkout and explicitly select fixture mode. Install the package from the checkout first. On Linux or macOS:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
mkdir -p /tmp/alltron-fixture-data
ALLTRON_DATA_DIR=/tmp/alltron-fixture-data python -m alltron --fixture-preview
```

In PowerShell:

```powershell
py -3.11 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -e .
$env:ALLTRON_DATA_DIR = Join-Path $env:TEMP 'alltron-fixture-data'
New-Item -ItemType Directory -Force -Path $env:ALLTRON_DATA_DIR | Out-Null
& .\.venv\Scripts\python.exe -m alltron --fixture-preview
```

Open **http://127.0.0.1:8765** on the same computer. Fixture mode is explicitly disconnected: it does not use Home Assistant, Codex, owner credentials, or voice engines. Use fictional labels and commands only; never point it at household data. The temporary data directory must remain outside the repository. The normal owner mode is separate and requires `--owner-profile` plus HTTPS.

## Current capability

| Capability | Today | Intended appliance |
| --- | --- | --- |
| Local dashboard | Runnable on a computer at loopback address | Full-screen Pi touchscreen |
| Timers | Durable timer state and browser chime | Service-owned alarms across browser and device restarts |
| Commands and lists | Explicit local time/timer/list commands; durable shopping items | Household commands and owner-selected HA entities |
| Home Assistant | Guided local OAuth UI and selected-entity flow implemented; live authorization and service behavior unaccepted | Dedicated Container, verified TLS, owner authorization, selected entities only |
| Voice | Opt-in service-owned push-to-talk adapters, unverified with live audio; wake disabled | Local wake/push-to-talk, Whisper and speech output |
| Alarms | Durable records and opt-in service tone; speaker behavior unverified | Verified service-owned playback and missed-alarm recovery |
| General answers | Hard-disabled pending isolation acceptance | Optional owner Codex CLI login only after isolated process acceptance |
| Installer | [Managed source archive and recovery](docs/PREVIEW_INSTALL.md); Linux service commands are implemented but activation is refused pending acceptance | Guided setup, diagnostics, backup and rollback |

Local household controls are designed to continue when answer services are unavailable. Codex answers are currently disabled. If enabled after isolation and privacy review, general questions would require network access and leave the device; see [privacy](docs/PRIVACY.md).

## Build order

Linux service preparation exists, but service activation and disposable Linux acceptance remain open. Separate-Pi validation is still the last technical gate before beta. See [stages](docs/STAGES.md), the [Linux services guide](docs/LINUX_SERVICES.md), and the [build plan](docs/BUILD_AND_RELEASE_PLAN.md). No result on the current household Pi is part of Alltron testing.

## Contribute and get help

Start with [installation](docs/INSTALL.md), [troubleshooting](docs/TROUBLESHOOTING.md), [architecture](docs/ARCHITECTURE.md), [Stage 2 development](docs/STAGE2_DEVELOPMENT.md), and [speech development](docs/VOICE_DEVELOPMENT.md). Contributions are welcome through [the contribution guide](CONTRIBUTING.md); every push follows the [publication privacy gate](docs/PUBLICATION_GATE.md). Use [support guidance](SUPPORT.md) for questions and [the security policy](SECURITY.md) for vulnerabilities. Never post household tokens, device identifiers, recordings, or private diagnostics in public issues.

Alltron-owned code is licensed under [GPL-3.0-only](LICENSE). Third-party voice engines, models, wake assets, and other redistributable components will be inventoried and reviewed before they are bundled.
