# Alltron software-first build and release plan

Evidence date: 2026-09-25. This plan describes the revised Stage 0–5 sequence in [STAGES.md](STAGES.md). The public preview includes timers, local commands, shopping state, opt-in speech/HA adapters and a fake-tested Codex transport. Stages 0–1 and the Stage 2 prototype are merged; live audio work remains in Stage 4 because no dedicated test Pi is available. Read-only reviews of the separate private speech pilot and full-release preview inform the design below; no Alltron software has been deployed to a Pi or verified as an appliance.

## Decisions

- Alltron lives in the separate public `jox218-source/Alltron` repository. Work on reviewable `codex/` branches. Never import the private project's Git history, source tree, household state or current-Pi connection details.
- The intended appliance installs Home Assistant Container on the same Pi. Each owner creates their own HA account and signs in to Codex CLI for optional general answers. The public edition omits personal-file search, PC gateway and local language-model serving.
- Keep a locally served touchscreen UI with a Python service. The service owns microphone capture, local Whisper transcription and speech playback; browser refresh must not interrupt the voice session.
- Finish the HA/Codex integrations, guided installer and desktop/VM simulations before purchasing or using a dedicated test Pi. Finish live voice and physical audio only on that separate Pi; software acceptance is not evidence of Pi latency or hardware support.
- The public code uses GPL-3.0-only. Review every bundled engine, model, voice, wake asset and copied component separately before distribution.

## Reuse and critical path

| Existing evidence or component | Use in Alltron | Work still required |
| --- | --- | --- |
| Public Alltron local preview, CI and publication gate | Extend the existing public package and keep its history/audit controls. | Connect owner integrations and setup; accept speech only on separate hardware. |
| Private app's command behavior, UI lessons and Pi speech results | Lead/reviewer writes a sanitized contract and acceptance checklist. Use reported failure modes to choose tests. | Implement Alltron modules cleanly; do not import private source, fixtures, model files, recordings, settings or Git history. |
| Upstream Whisper/Piper engines and candidate voice profiles | Keep the current optional adapters behind truthful readiness indicators. | Select assets, verify exact licenses/model provenance and measure ARM64 full-load behavior in Stage 4 before a default is promised. |
| Existing Home Assistant Container experience | Define the supported same-Pi topology and known setup checks. | Build owner onboarding, authorization, selected-entity controls and fresh-install tests. |
| Private full-release preview | Use only the observed contracts: explicit archive inventory/hashes, staged install/rollback, private HA selection/configuration, and voice asset/health checks. The Alltron source-archive slice is implemented in open PR #9; it was independently checked against committed public Git blobs. | Review the public archive slice and continue with preflight, install/rollback, owner setup and fictional tests. Install HA on the same device, prove repeat installs/recovery and review every redistributed asset. The private preview targets a different topology and has no fresh second-Pi acceptance. |
| Existing private PC answer route | Retain only the lesson that answers must be isolated from household mutations. | Build a new restricted Codex adapter; no PC gateway or personal-file route. |

The shortest dependency path now is: Stages 0–1 and the Stage 2 prototype (merged); finish disposable HA authorization and isolated Codex trial (Stage 2) **while** completing Alltron's Stage 3 preflight and rollback after the open source-archive PR #9; join them for a clean disposable Linux install and independent software setup trial; then run dedicated-Pi live speech/full-stack acceptance (Stage 4) before beta (Stage 5). Wake integration, resident Piper, real microphone/speaker selection, spoken end-to-end checks and ARM64 performance remain Stage 4 gates. The private preview shortens design discovery, not public implementation, licensing review or acceptance.

The proposed first-beta path is durable timers/alarms, selected Home Assistant controls and lists, local push-to-talk and wake speech, and optional signed-in Codex answers. Calendar, weather and other private-app features may proceed as separate public modules but do not delay this core acceptance path; each needs its own owner setup and tests before inclusion in a release. This scope is a planning choice, not a claim that those modules already exist.

## What the private speech pilot changes

The private app now has a Pi-local Whisper worker and Piper speech worker. Its reported Pi tests include successful short-command transcription and a spoken clock response through the wake path. A resident Piper candidate produced much faster first audio than a fresh CLI process in its earlier isolated benchmark. The current app still routes some speech and answers through its PC gateway; Alltron needs a fresh local voice route and its separate Codex answer adapter. These results support a service-side speech design, but they do not establish Alltron's latency, accuracy or memory with Home Assistant, Codex and kiosk running together.

The pilot also exposed two design traps. Its wake listener releases the microphone before Chromium opens it, so capture can lose speech or pick up the listening cue. Its first STT activation used a nonspeech tone and timed out under the worker's CPU quota despite direct transcription working. Alltron therefore keeps one service-owned microphone stream through wake and utterance capture, and verifies recognition with a known-good spoken sample. A worker-ready indicator alone is insufficient: setup must also prove mic capture, recognized text, command routing, audible reply, cancellation and recovery.

This is a design comparison only. No private code, model, recording, device setting or deployment artifact enters Alltron. The physical test Pi remains the final technical gate. Do not promise Pi 4 support or choose a bundled voice, wake model or performance default from this pilot alone.

## What the private full-release preview changes

Read-only inspection found a deterministic archive with an explicit file inventory and hashes; a staged core installer with a health-checked rollback path; a helper that selects Home Assistant entities and saves private configuration; and voice provisioning that checks binary/model provenance and worker health. Those are useful behavior and test contracts. They allow Stage 3 packaging and recovery work to begin now instead of waiting for every Stage 2 connection to finish. In Alltron, author a new package builder, installer and tests from the public source tree and fictional fixtures. Keep all credentials and model weights outside the archive and require a separate source/license review for art, audio, models and dependencies.

The private candidate connects to an already running Home Assistant instance and uses a separate PC answer gateway. It does not implement Alltron's same-Pi HA install, owner Codex CLI path, public setup flow or hardware acceptance. Its private code, docs, identifiers, assets, ZIP and Git history must not be imported or used as a public release base. The public Alltron timer/voice preview remains the only application implementation foundation.

The focused private-preview check passed 9 of 10 tests on Windows. Its time-zone-sensitive helper test lacked the expected IANA data in that Python environment; this is unresolved test-environment evidence, not proof of a Pi failure. Stage 3's disposable Linux rehearsal must cover the equivalent behavior with fictional Alltron fixtures and recorded time-zone data.

## Boundary from the private installation

The existing household Pi and Home Assistant remain untouched. The lead/reviewer may inspect private source read-only solely to select design ideas; public code is written cleanly within Alltron. Same-host worktrees do not isolate agents from private files, so same-host Luna work is restricted to public docs, fictional fixtures, UI and other approved nonsensitive modules. Sensitive implementation requires the lead or a separate OS/container environment without private mounts, credentials or SSH configuration. No Alltron install script may target the current Pi. Remote install is prohibited until an exact dedicated test-device allowlist is recorded.

## Target architecture

```text
Pi touchscreen ──loopback──> Alltron API and durable state
                         ├─ timers, alarms and deterministic command router
                         ├─ selected Home Assistant entities ──> local HA Container
                         ├─ voice: wake/push-to-talk → Whisper → router → Piper
                         └─ isolated text-answer adapter ──> owner Codex CLI login
```

The browser handles touch and setup. A service-owned audio process keeps one microphone stream across wake detection and utterance capture, including browser refresh; it pauses detection during playback and resumes afterward. A separate bounded inference worker can expose independent STT/TTS health, request IDs and cancellation over a local socket. Household mutations pass through a local, typed command router and owner-selected entity/action allowlist. The answer adapter receives bounded question text and cannot directly reach HA actions or credentials. It runs under a restricted OS identity with isolated configuration, empty working directory, timeouts and no plugins/MCP integrations. Codex CLI is a coding-agent interface; suitability and isolation must be tested before enabling it by default on a Pi. Account or usage restrictions may make it unavailable for some owners. No general-answer text is executed as a household command.

The ordinary API must not run as root or receive the Docker socket. A minimal privileged installer helper may perform only named install/update/rollback operations after validating caller, paths, versions and verified artifacts. The HA token stays server-side with restrictive permissions and revocation support. The owner uses HA's account onboarding and authorization flow; the UI must never ask for an HA password. A manual token may be a labeled development fallback only.

## Work allocation for the compressed stages

| Stage | GPT-6 Luna Medium implementation | GPT-6 Sol High review | Evidence to leave behind |
| --- | --- | --- | --- |
| 0: boundary/reuse | Fictional fixture catalog, public docs and acceptance checklist from approved contracts. | Lead/Sol compare private observations read-only, review licensing and the public path/history boundary. | Sanitized checklist, reviewed paths and exact-SHA audit on every push. |
| 1: local foundation | UI, typed commands, durable alarms/lists and fake-device voice harness under approved contracts. | Command idempotency, one mic owner, cancellation and event/health contract. | Merged local timer/command/voice tests and restart recovery; no live speech claim. |
| 2A: HA closeout | Fictional discovery/selection UI and disposable HA fixtures under the public contract; prototype router already merged. | Owner authorization, credential lifecycle, allowlist and ambiguous-write behavior. | Same-device disposable HA install, synthetic actions, outage, revocation and reauthorization tests. |
| 2B: Codex closeout | Owner status UI and fake failure fixtures; fake transport already merged. Sensitive runner implementation stays with lead/Sol until isolated. | Process/mount/network boundary, auth cache, custom config/plugins, prompt-to-shell paths and failure messaging. | Disposable signed-in trial with timeout, cancellation, usage/network/auth tests and no secrets in logs. |
| 3: portable release, parallel start | Public-only archive fixture/tests, wizard and redacted status UI under agreed contracts. | Installer privilege boundary, exact archive inventory, idempotency, recovery and asset licensing. | Re-authored package/preflight/rollback, clean disposable Linux/HA install, repeat/failed update, fake audio and independent software setup trial. |
| 4–5: physical voice gate/beta | Finish wake/resident speech and exact asset selection on a separate Pi; then apply hardware findings to release prep. | Live capture/playback, dependency provenance, full-load hardware, security, privacy, license, archive and release-candidate review. | Supported profile, spoken mic-to-reply path, alarm sound, independent fresh-owner install and reviewed beta archive. |

The lead fixes contracts, integrates scoped work and owns physical acceptance and publication decisions. Luna Medium agents may work in parallel on non-sensitive public UI, fixtures, docs and tests on this host; sensitive implementation requires an Alltron-only OS/container environment without access to the private projects or credentials. Agents do not edit the same files concurrently. Every public push repeats the privacy gate in [STAGES.md](STAGES.md).

## Foolproof owner experience to reach before beta

1. A versioned, checksum-verified release checks Pi model/RAM, OS, free storage, audio/display devices, network and Docker availability and gives a plain-language remedy for failures.
2. Installer performs idempotent named steps and offers uninstall/rollback. A failed update restores the prior working release and saved household state.
3. First-run wizard starts HA, hands account creation to HA, completes owner authorization, selects controllable entities and tests an action. It then handles Codex login under the restricted identity and verifies a harmless answer. No credential is pasted into a public issue or stored in the browser.
4. Audio check shows the selected input and output devices, input level, output test, mute state and push-to-talk fallback. Setup cannot mark voice complete until a spoken test passes from the selected microphone through transcription and audible reply. It reports wake, STT and TTS separately; optional wake mode requires an additional normal-volume test.
5. Health screen distinguishes local service, HA, audio and answer-provider failures, with recovery steps and a one-click **redacted** diagnostics bundle.
6. Automated acceptance covers reboot, browser refresh, service restart, unplugged mic, HA outage, network loss, auth expiry, low disk and interrupted update. Independent testers complete a fresh install from the public docs.

These are release criteria, not current features. The exact hardware, wake word, voice assets and beta feature set remain configurable decisions until validated.

## Public GitHub sequence

1. Publish small, audited development branches with an honest pre-alpha README, code, tests, contribution/security/support docs and issue templates. Keep `main` release claims tied to merged evidence.
2. Require CI and review for PRs; enable secret scanning/push protection and dependency alerts if the repository/account settings support them. These controls supplement the pre-push source and history audit.
3. Publish installable prereleases only after the installer and simulated acceptance are complete. Release beta only after dedicated-Pi and independent owner acceptance. Document supported hardware and limits on that release, not in advance.

## Sources checked for the original design

- Codex authentication and noninteractive mode: https://learn.chatgpt.com/docs/auth and https://learn.chatgpt.com/docs/non-interactive-mode (checked 2026-09-22).
- Home Assistant authorization and Pi Container installation: https://developers.home-assistant.io/docs/auth_api/ and https://www.home-assistant.io/installation/raspberrypi-other/ (checked 2026-09-22).
- GitHub repository security settings: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-security-and-analysis-settings-for-your-repository (checked 2026-09-22).
