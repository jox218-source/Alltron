# Architecture

## Status

This document separates the current developer preview from the proposed appliance architecture. The Python preview now serves a loopback-only HTTP UI/API, stores timer state in SQLite, and can play a short browser chime when a timer finishes while the page is open and the browser allows audio. It is not a Pi-tested appliance. Home Assistant, Codex, Whisper, microphone capture, service-owned alarms/speech, service units, and an installer remain unimplemented. The dedicated Pi feasibility gate remains open.

## Intended deployment

The target is one Raspberry Pi running the Alltron application and Home Assistant Container. A locally served touchscreen page communicates with an Alltron service. Local speech recognition and speech playback are intended to remain on the Pi. General questions may be sent through the owner's Codex CLI account, subject to confirming that the CLI can be isolated and operated reliably on the selected Pi. The current private Home Assistant installation and PC gateway are outside this project.

## Current developer preview

The Python 3.11+ package has no third-party runtime dependencies. `alltron` starts a standard-library threaded HTTP server bound to `127.0.0.1`; `alltron --check` prints local preflight information and exits. The service exposes a health endpoint, a timer list/create/cancel API, and serves the bundled UI assets. Timer records are stored in SQLite under the local data directory (overridable with `ALLTRON_DATA_DIR`). The browser plays a brief chime when a timer finishes if the UI page is open and browser audio is allowed. This page-local chime is not a service-owned Pi alarm: closing the page or browser prevents it from sounding. The preview does not run a wake-word detector, transcribe speech, call Home Assistant, or call Codex.

Contributor setup and run instructions are in [Installation](INSTALL.md). The preview must remain on loopback; its HTTP interface is not designed for LAN or internet exposure.

The preview endpoints are `GET /api/health`, `GET /api/timers`, `POST /api/timers`, and `POST /api/timers/cancel`. They support timer status, creation, and cancellation only. The health response marks Home Assistant, Codex, and voice as not configured.

```text
Touchscreen / kiosk
        │ local connection
        ▼
Alltron application
  ├── deterministic command router ──> owner-selected Home Assistant entities (planned)
  ├── local durable timer state (preview)
  ├── local audio pipeline (planned: wake/capture → Whisper → response → speech)
  └── isolated answer adapter (planned: bounded text request → Codex CLI)

Home Assistant Container runs on the same Pi as a separate service.
```

## Security boundaries to preserve

- The browser must not receive Home Assistant or Codex credentials. Credential storage and authorization flows are not implemented.
- Home Assistant actions should go through a deterministic local router and an owner-selected entity/action allowlist. General LLM output must not trigger actions directly.
- The Codex answer process should receive only the bounded question text it needs. It must not receive Home Assistant credentials, microphone access, household files, or unnecessary privileges. Process isolation is a design requirement pending feasibility tests.
- Logs and support bundles must exclude tokens, private audio, and personal household content by default.
- The installer and any privileged helper require a reviewed, narrow permission boundary. Neither currently exists.

These are target constraints, not verified properties of a running system. See the [build and release plan](BUILD_AND_RELEASE_PLAN.md) for gates and unresolved design decisions.

## Components and current implementation state

| Component | Intended responsibility | State |
| --- | --- | --- |
| Touchscreen UI | Setup, touch controls, health and recovery guidance | Basic developer preview UI for timers; owner setup/recovery UI is planned |
| Application service | Local API, configuration, orchestration and persistence | Loopback preview server and timer persistence implemented; appliance orchestration is planned |
| Household command router | Validate requests and call selected HA entities | Planned; no adapter or allowlist |
| Home Assistant | Run as a container on the same Pi; owner creates account and authorizes Alltron | Deployment target only; no installer or auth flow |
| Audio | Pi-owned microphone path, local Whisper transcription, local speech output, push-to-talk fallback | Not implemented; hardware and asset choices unverified |
| Codex answers | Restricted CLI process for bounded general questions | Feasibility gate; no adapter |
| Installer / updater | Prerequisite checks, setup, backup, update and rollback | Planned; no installer or helper |

## Data flow target

Typed or transcribed input should first enter the local router. Supported household commands are parsed and validated locally before reaching Home Assistant. An ordinary question may go to the Codex adapter, which returns text for local display or speech. A model answer must never be treated as an authorized Home Assistant command. Timers should be stored locally so they survive a service restart.

In the developer preview, timer requests flow from the local UI to the loopback API and SQLite store. Timer state is durable across service restarts. When the page is open and audio is allowed, the browser plays a chime after it observes a timer marked done. There is no service-owned alarm or Pi speech output, so the chime is not guaranteed when the page is closed, suspended, or audio is blocked. The broader household data flow above is a design target; its behavior has not been implemented or measured. Offline behavior, retention periods, telemetry policy, and the exact authorization method remain release decisions that must be settled and documented before beta.
