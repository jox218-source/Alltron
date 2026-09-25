# Troubleshooting

## Current status

Alltron is pre-alpha. A local preview has timers, typed commands, shopping items and opt-in speech adapters, but there is no Pi appliance installer, Home Assistant or Codex integration, accepted live speech path, or supported hardware profile. The entries below distinguish preview behavior from future recovery requirements.

## Run the local timer preview

Follow the contributor setup in [Installation](INSTALL.md), then run `alltron --check` to confirm the Python environment and local data path. Start the service with `alltron` and open `http://127.0.0.1:8765` on the same computer. The service prints its URL and exits cleanly with Ctrl+C. It binds to loopback only.

## `alltron` is not found after installation

Make sure the virtual environment is active in the same terminal where you installed the package. From the repository root, run `python -m pip install -e .` again. You can also call the module directly with `python -m alltron`.

## The default port is already in use

Start the preview with a different port, for example `alltron --port 8766`, then open `http://127.0.0.1:8766`. The preview validates the port range and reports a startup error if the selected port cannot be bound.

## Timers disappeared or are missing

Timer records are kept in the local SQLite database under the preview data directory. `alltron --check` prints the directory being used. If `ALLTRON_DATA_DIR` is set, the preview reads and writes the database in that alternate folder. Keep using the same data folder between runs. The preview does not yet include backup, restore, or migration tools.

## A timer is marked done

The preview updates a running timer to `done` when its due time has passed and the timer list is requested. Timer labels must contain 1 to 80 characters, and durations must be whole seconds from 1 second through 24 hours. If the page is open and browser audio is allowed, the page plays a short chime when it observes a finished timer. This is browser audio, not a service-owned alarm; it may not sound if the page or browser is closed, suspended, or blocking audio. The preview does not provide Pi speech output or control household devices.

## The project says Raspberry Pi but gives no model

Hardware support is not established. The separate test Pi is not yet available. A supported model, RAM size, operating system, display, microphone, speaker, and storage profile will be published only after concurrent audio, Home Assistant, and kiosk tests pass on that device.

## Voice controls are disabled or fail

Voice is disabled by default. This preview needs a service-owned ALSA input, local Whisper/Piper tools and models, and a selected output before the corresponding health states can become ready. A path check is not a spoken setup test. See [speech development](VOICE_DEVELOPMENT.md); do not place recordings or model assets in a public issue. Wake detection is still disabled.

## Account setup does not work

Guided Home Assistant authorization and Codex CLI sign-in integration are not implemented. The opt-in Home Assistant prototype reads a private token file and reports `not-allowed`, `auth-error`, `service-error` or `unavailable` without returning the token or raw server response. Check the owner config and token permissions locally; revoke a compromised token in Home Assistant. Speech and alarm adapters exist but have not passed live Pi acceptance. Do not share credentials or tokens to diagnose the project. Future setup diagnostics should distinguish authorization, network access, account limits and service failure without printing credential contents.

## How to report a future bug

Before filing an issue, check existing issues and include the Alltron release or commit, operating-system and hardware versions, the exact step that failed, and the visible error text. Remove names, addresses, entity IDs, IP addresses, tokens, audio, and household details. Do not attach raw logs or support bundles until the project documents a redaction procedure. For suspected security vulnerabilities, use the repository's private reporting route once one is published; never post credentials or exploit details in a public issue.

## Recovery expectations for the planned appliance

Before beta, Alltron needs documented and tested recovery for interrupted setup or updates, unavailable Home Assistant, expired/revoked authorization, missing audio devices, Codex sign-in or usage-limit failures, network loss, disk pressure, and service restart. The intended UI should identify the failing component, preserve household data during recovery, and give one safe next step. Until those paths exist and are tested, Alltron should not be described as idiot-proof or ready for household use.
