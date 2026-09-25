# Changelog

Alltron is in pre-alpha. Entries describe development work, not verified Raspberry Pi support.

## 0.1.0a0 — Unreleased

- Added an opt-in owner-token Home Assistant light/switch allowlist prototype, a disposable container recipe, and a fake-tested Codex answer transport. Live HA and signed-in Codex acceptance remain open.
- Moved wake, resident speech, live microphone/speaker checks and ARM64 voice acceptance to the separate-Pi Stage 4; Stage 2 HA/Codex owner integrations are the next software work.
- Documented PR #1's already-public squash-merge author-email exposure and limited the publication audit exception to that exact commit SHA; new commits still require no-reply identities.
- Began Stage 1 from the public timer preview: explicit local commands, shopping-list state, alarm records and opt-in service tone, plus simulated speech and a service-owned push-to-talk path. Wake detection and physical speech acceptance remain open.
- Added the sanitized reuse checklist and narrowed the roadmap to stages 0–5; the private app and Pi remain outside Alltron development.
- Added the Stage 0 publication gate: exact public path manifest, full post-root commit and blob audit, no-reply identity checks, historical secret scanning and CI enforcement.
- Added an optional local pre-push guard and protected GitHub `main` with PR and privacy/test checks.
- Added a loopback-only Python developer preview with a local dashboard and durable SQLite timers.
- Added a browser chime for completed timers while the page is open, plus health and timer APIs.
- Added package installation, automated tests, CI, contributor and security files, and preview installation/troubleshooting docs.
- Reordered the roadmap so dedicated Pi validation follows software build and simulated acceptance and precedes beta.

Home Assistant installation/control, Codex answers, Whisper, service-owned audio, guided owner setup and Pi hardware validation remain future work.
