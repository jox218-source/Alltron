# Architecture

## Status

This document separates the current developer preview from the proposed appliance architecture. The loopback-only Python preview stores timers, alarms and shopping items in SQLite, routes a small explicit local command set, and can play a browser timer chime while the page is open. Opt-in adapters support service-owned push-to-talk capture, local Whisper/Piper CLI calls and a generated service alarm tone. Stage 2 adds an opt-in Home Assistant light/switch adapter and a fake-tested Codex answer transport. These adapters have only simulated tests: no live speech, real Home Assistant, signed-in Codex or Pi hardware profile is accepted, and wake detection remains disabled. Service units and an owner installer remain unimplemented.

## Intended deployment

The target is one Raspberry Pi running the Alltron application and Home Assistant Container. A locally served touchscreen page communicates with an Alltron service. Local speech recognition and speech playback are intended to remain on the Pi. General questions may be sent through the owner's Codex CLI account, subject to confirming that the CLI can be isolated and operated reliably on the selected Pi. The current private Home Assistant installation and PC gateway are outside this project.

## Current developer preview

The Python 3.11+ package has no third-party runtime dependencies by default. `alltron` starts a standard-library threaded HTTP server bound to `127.0.0.1`; `alltron --check` prints local preflight information and exits. The service exposes health, timer, alarm, shopping-list, typed-command and opt-in voice-control endpoints. One SQLite file under `ALLTRON_DATA_DIR` holds durable local state. The browser timer chime still requires an open page; a separate service alarm tone needs a selected ALSA output and remains unverified on Pi. The preview has no wake-word detector, Home Assistant call or Codex call.

Contributor setup and run instructions are in [Installation](INSTALL.md). The preview must remain on loopback; its HTTP interface is not designed for LAN or internet exposure.

The preview keeps the timer endpoints and adds `GET/POST /api/alarms`, `POST /api/alarms/cancel`, `GET/POST /api/lists/shopping`, `POST /api/lists/shopping/complete`, `POST /api/commands`, and opt-in `POST /api/voice/{start,stop,cancel}` with `GET /api/voice/events`. The browser sends only control events for voice; the local service owns microphone capture. Health reports Home Assistant as configured only when an owner supplied private configuration has loaded; Codex remains unconfigured in the running service. Voice wake/capture/STT/TTS have separate disabled, unavailable or ready statuses with a verification flag where applicable. A configured path check is not full service acceptance.

```text
Touchscreen / kiosk
        │ local connection
        ▼
Alltron application
  ├── deterministic command router ──> owner-selected HA light/switch aliases (prototype)
  ├── local durable timer state (preview)
  ├── local audio pipeline (planned: wake/capture → Whisper → response → speech)
  └── answer adapter (fake-tested; isolated Codex CLI process planned)

Home Assistant Container runs on the same Pi as a separate service.
```

## Security boundaries to preserve

- The browser must not receive Home Assistant or Codex credentials. The HA prototype reads an owner-created token from a private file outside the repo. A guided authorization and credential lifecycle are not implemented.
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
| Household command router | Validate requests and call selected HA entities | Explicit local grammar and opt-in light/switch alias allowlist implemented; fake HA tested |
| Home Assistant | Run as a container on the same Pi; owner creates account and authorizes Alltron | Disposable test compose file and token-file prototype; no live instance, installer or guided auth flow |
| Audio | Pi-owned microphone path, local Whisper transcription, local speech output, push-to-talk fallback | Opt-in local adapters and simulated tests; wake, asset selection and live acceptance open |
| Codex answers | Restricted CLI process for bounded general questions | Fake-tested adapter and CLI transport; not wired into the running service pending isolation gate |
| Installer / updater | Prerequisite checks, setup, backup, update and rollback | Planned; no installer or helper |

## Data flow target

Typed or transcribed input should first enter the local router. Supported household commands are parsed and validated locally before reaching Home Assistant. An ordinary question may go to the Codex adapter, which returns text for local display or speech. A model answer must never be treated as an authorized Home Assistant command. Timers should be stored locally so they survive a service restart.

In the developer preview, timer and list requests flow from the local UI to the loopback API and SQLite store. Timer state is durable across service restarts. The browser chime may be missed when the page is closed or audio is blocked. An opt-in alarm service tracks `played` versus `missed` separately; its speaker output has not passed physical acceptance. Optional voice capture sends transient PCM from the service microphone to local Whisper, passes the transcript through the explicit local router and can speak the response through Piper. No recording is sent to Home Assistant or Codex; if HA is configured, the recognized command text may cause a selected service action. Codex answers remain disabled in the service. Offline behavior, retention periods, telemetry policy and owner authorization still need release decisions before beta.
