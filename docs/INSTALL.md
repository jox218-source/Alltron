# Installation

## Current status

**Alltron is pre-alpha.** The repository now contains a local Python developer preview for durable timers. It is not an appliance installer, and it does not install Home Assistant or connect to Codex, Whisper, a microphone, or a speaker. A dedicated Raspberry Pi has not yet been tested, so there is no supported Pi/OS combination to recommend. Do not install this preview on the household Pi.

The commands below run the developer preview on a computer with Python 3.11 or newer. The owner installation guide for the future Pi appliance will be written after its installer and recovery path are implemented and tested on a dedicated device. The intended first setup is designed to install Home Assistant Container on the same Pi, then guide the owner through Home Assistant authorization and their own Codex CLI sign-in. Neither account flow is implemented yet.

## For contributors

You can review the design and propose changes through GitHub. The package currently has no third-party runtime dependencies. Python 3.11 or newer and pip are required to create the local environment and install the preview.

### Windows PowerShell

From the repository root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
alltron --check
alltron
```

If PowerShell blocks virtual-environment activation, use the platform's documented Python activation guidance or run the executable directly as `& .\.venv\Scripts\alltron.exe --check` and `& .\.venv\Scripts\alltron.exe`.

### Linux / Raspberry Pi OS / macOS

From the repository root with Python 3.11 or newer:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
alltron --check
alltron
```

The `--check` command prints the Python version, timer data directory, and preview mode, then exits without starting the server. The default server URL is `http://127.0.0.1:8765`. Open that exact loopback address in a browser on the same computer. The health endpoint is `http://127.0.0.1:8765/api/health`. Stop the server with Ctrl+C in its terminal. You may choose another port with `alltron --port 8766`; use the matching URL `http://127.0.0.1:8766` and health endpoint `http://127.0.0.1:8766/api/health`.

Timer state is stored in SQLite at `~/.local/share/alltron/timers.sqlite3` on Linux/macOS or the platform home directory's `.local/share/alltron/timers.sqlite3` path on Windows. To use a different data folder for one run, set `ALLTRON_DATA_DIR` before launching. In PowerShell: `$env:ALLTRON_DATA_DIR = 'C:\AlltronData'`; in a POSIX shell: `ALLTRON_DATA_DIR="$HOME/alltron-data" alltron`. On POSIX, Alltron creates its data folder for owner access (0700) and the database for owner read/write (0600); if an existing folder or database is readable by other users, startup stops and asks you to correct permissions. It does not change permissions on an existing shared folder. Keep the folder private on every platform; timer labels may contain household information. The preview has no backup or migration tool yet, so do not treat this database as protected household data.

The preview binds only to `127.0.0.1`; it is not accessible to other devices on the LAN. Do not change the bind address or put it on the public internet.

This preview assumes a trusted, single-user computer. Other local processes may reach the loopback API; do not use it for sensitive household information on a shared machine.

## Planned owner setup

The following sequence is a design target, not a working procedure:

1. Confirm the exact Pi, storage, display, microphone, speaker, network and operating-system versions are on Alltron's tested hardware list.
2. Back up the Pi and follow a versioned installer that checks the device and prerequisites before making changes.
3. Open the local setup screen and create the Home Assistant owner account using Home Assistant's own setup flow.
4. Authorize Alltron from Home Assistant. Alltron must never ask for the owner's Home Assistant password.
5. Sign in to Codex CLI using the account's supported device login flow, then run a harmless connection check.
6. Select the Home Assistant entities Alltron may control, run microphone/speaker checks, and confirm a test action.
7. Verify the health screen, reboot recovery, backup location, and uninstall instructions before enabling unattended use.

The installer must stop with a plain-language explanation when a check fails. It must not silently skip a failed security or hardware check, and it must provide a supported recovery path before beta.

## Before a future install

When installation becomes available, use only a tagged release and the commands published on that release's page. Read the release's hardware support list, privacy notes, upgrade instructions, and rollback steps first. Never paste Home Assistant tokens, Codex credentials, or diagnostic bundles into a public issue.
