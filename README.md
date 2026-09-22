# Alltron

**An open-source household assistant being built for a Raspberry Pi.**

Alltron aims to combine local voice, timers, a touchscreen, Home Assistant controls, and optional general answers through each owner's Codex CLI login. The intended appliance installs Home Assistant Container on the same Pi. Owners will bring their own accounts. Personal-file search and the original private household setup are outside this public project.

> **Pre-alpha:** the repository currently contains a runnable **local timer developer preview**, not a ready-made Pi appliance. Raspberry Pi hardware, voice, Home Assistant installation/control, Codex sign-in, and one-step owner setup have not been verified. Do not install this preview on a production household Pi.

## Try the developer preview

Python 3.11 or newer is required. From a clean checkout:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -m alltron --check
python -m alltron
```

Open **http://127.0.0.1:8765** on the same computer. The preview serves a local dashboard and durable timers; timer records are stored in `~/.local/share/alltron/timers.sqlite3` by default. Its browser chime works only while the page is open and the browser permits audio. On Windows, use [the PowerShell steps](docs/INSTALL.md) instead of the shell activation command above. The preview has no third-party runtime dependencies.

## Current capability

| Capability | Today | Intended appliance |
| --- | --- | --- |
| Local dashboard | Runnable on a computer at loopback address | Full-screen Pi touchscreen |
| Timers | Durable timer state and browser chime | Service-owned alarms across browser and device restarts |
| Home Assistant | No connection or controls | Installed on the Pi, owner authorization, selected entities only |
| Voice | No microphone or transcription | Local wake/push-to-talk, Whisper and speech output |
| General answers | No account login or answer calls | Optional owner Codex CLI login with isolated answer process |
| Installer | Manual developer preview setup | Guided setup, diagnostics, backup and rollback |

Alltron is designed so local household controls can continue when the answer service is unavailable. General questions sent to Codex will require network access and will leave the Pi. The exact data handling and offline guarantees must be verified before beta; see [privacy](docs/PRIVACY.md).

## Build order

We are doing software implementation, simulation, setup design, and automated acceptance **before buying or using a dedicated test Pi**. Physical Pi validation is the last technical gate before beta. See [stages](docs/STAGES.md) and the [build plan](docs/BUILD_AND_RELEASE_PLAN.md). No result on the current household Pi is part of Alltron testing.

## Contribute and get help

Start with [installation](docs/INSTALL.md), [troubleshooting](docs/TROUBLESHOOTING.md), and [architecture](docs/ARCHITECTURE.md). Contributions are welcome through [the contribution guide](CONTRIBUTING.md); every push follows the [publication privacy gate](docs/PUBLICATION_GATE.md). Use [support guidance](SUPPORT.md) for questions and [the security policy](SECURITY.md) for vulnerabilities. Never post household tokens, device identifiers, recordings, or private diagnostics in public issues.

Alltron-owned code is licensed under [GPL-3.0-only](LICENSE). Third-party voice engines, models, wake assets, and other redistributable components will be inventoried and reviewed before they are bundled.
