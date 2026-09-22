# Alltron build and public development plan

Evidence date: 2026-09-22. Status: planning artifact. Nothing in this plan has been installed on the existing private Pi, merged into `main`, pushed to GitHub, or verified as a public release.

## Decision record

- Build Alltron as a separate Raspberry Pi household appliance in `jox218-source/Alltron`. The GitHub repository is already public and currently has one commit and a one-line README. Develop on public `codex/` branches with small pull requests and explicit pre-release labels; never import the private project's Git history.
- The first supported path installs Home Assistant Container on the same Pi. Each owner creates their own HA account and authorizes Alltron. The public edition has no personal-file answers, PC gateway, LM Studio, or Gemma.
- Keep the locally served TypeScript touchscreen UI and Python service. Move microphone capture, wake handoff, transcription, and speech playback into Pi services. Use the owner's Codex CLI login for general answers, subject to a physical-Pi and account-compatibility feasibility gate.
- Pending owner answers: first supported hardware target and public wake-word/voice defaults. Until decided, both remain configurable design inputs, not release promises.
- The owner reported no separate test Pi is currently available. The current household Pi remains off limits. Clean scaffolding, fictional fixtures, mocked integration tests and setup design can proceed now; physical feasibility and any supported-hardware claim wait for dedicated test hardware.
- Proposed license: GPL-3.0 for Alltron-owned source, since the intended Piper engine is GPL-3.0 and this keeps the planned integrated distribution simpler to reason about. This is a recommendation, not a completed license/provenance review. Audit copied source ownership and the exact Piper, voice, wake-model, Whisper and other redistribution terms before adding `LICENSE` or shipping assets. Do not bundle model weights or household media before that review.

## Mechanical separation from the private installation

1. Work in this separate clone and its `codex/` branches only. The lead/Sol may inspect the private source read-only to create an approved source-file manifest. Give Luna implementation agents a separate OS/container environment containing only Alltron, fictional fixtures and that manifest, without private directories, credentials or SSH configuration. A same-host worktree is insufficient because collaboration agents share the host filesystem. Until true isolation exists, reserve private-source selection and sensitive implementation/audit work for lead/Sol; same-host Luna work is limited to nonsensitive fixtures, UI and docs. No symlinks, Git submodules, deployment scripts, or runtime imports may point into the private project.
2. Start a new public file tree from an allowlist: household domain logic, deterministic commands, weather, calendar, alarm tones, API guard patterns, selected UI components and tests. Rewrite the public API boundary. Exclude the library bridge, PC gateway, personal index, photos, pairings, tokens, model files, built ZIPs, and all local state.
3. Add a denylist-based secret and personal-data scan as a second check, not the primary selection mechanism. Before any public push, inspect all branch commits and Git objects from the public one-commit base, not just staged files. Ensure test fixtures use fictional names, entities, addresses, time zones and calendar events.
4. Keep development tests and future installs on a separately identified test device. Install scripts must require an exact, recorded test-device identity from an allowlist and refuse the current household Pi. No agent may run `scp`, `ssh`, `systemctl`, or Docker commands against the current household Pi.

## Architecture target

```text
touchscreen/kiosk ──localhost──> Alltron API and state
                                 ├─ durable timers and alarms
                                 ├─ validated household command router ──> selected HA entities
                                 ├─ voice service: wake → capture → local Whisper
                                 │                  → router/answer → local Piper
                                 └─ isolated Codex answer adapter ──internet──> owner's account

Home Assistant Container runs separately on the same Pi.
```

The browser provides setup, touch controls and status. The voice service owns the microphone so a browser refresh does not break an utterance. Household mutations are validated locally against an owner-selected entity/action allowlist. Codex answers are text only; the Codex process has no HA credential, audio device, elevated OS privilege, household files, plugins or MCP integrations. The CLI can invoke read-only shell tools, so use a dedicated OS user and, if validated on the target OS, a process/container boundary with only an empty working directory and required network access. Also use Codex's read-only sandbox, ignored user/project configuration, bounded context, structured final output, timeout and cancellation. Test that these controls actually hold on Linux ARM64. A general answer must never cause a direct HA action.

The web/API service must have no Docker socket or root privilege. A separate, minimal privileged helper performs only named install/update/rollback operations from verified release artifacts; it checks caller identity, validates paths and versions, and reports structured results. Define and threat-model this helper before building the wizard. Home Assistant authorization tokens are sensitive even when Alltron restricts which entities it uses: a stolen token may permit broader HA access under that user, so store it outside the browser and ordinary logs with strict permissions and revocation support.

The Home Assistant setup wizard starts the container, opens HA's own account onboarding, then asks the owner to authorize Alltron. Prototype HA's authorization-code and refresh-token flow with its redirect constraints; use a manual long-lived access token only as a clearly labeled development fallback. The owner selects lights, to-do entities and an optional writable calendar. Time zone and calendar names become configuration, not fixed household defaults. The public UI never asks for or stores the HA password.

Codex setup uses the documented `codex login --device-auth` flow when available, with the URL/code shown on the screen for completion on another device. Run login under the same restricted identity used by the answer adapter. Verify status and a harmless sample answer. Provide reconnect/logout, distinguish auth/limit/network failures and never place the credential cache in Git, UI responses, logs or support bundles. Device-code login is beta and may be disabled by account/workspace settings. `codex exec` is a coding-agent interface, so its suitability for a household service is a go/no-go prototype question. Do not imply that an ordinary ChatGPT login guarantees this feature.

## Work packages and agent assignments

Each Luna task is a small branch or scoped commit in **Alltron only**, with tests/fixtures and a handoff note. The lead integrates work after the stated Sol review. GPT-6 Sol High reviews sensitive contracts **before** Luna implementation and reviews final diffs afterward; it does not substitute a passing test or physical hardware result. The lead/Sol owns private-source selection, isolation design, feasibility decisions and public push audits.

| Stage | GPT-6 Luna Medium implementation assignment | GPT-6 Sol High review gate | Exit evidence |
| --- | --- | --- | --- |
| 0 | Prepare the approved file manifest and fictional fixtures only after the privacy boundary is defined. | Own the private-source selection, commit-metadata check and full history audit before the first public push. | No private source, state, media or credentials in the Alltron tree or branch history. |
| 1 | Build fictional benchmark fixtures/harnesses and a clean Python/UI scaffold from the approved manifest; no copied private tree or history. This can begin without a test Pi. | Review contracts, hardcoded personal terms, API boundaries and CI secret exposure before implementation and push. | Clean public tree builds; no runtime dependency on the private project. |
| 2 | Run the three feasibility spikes on a **dedicated test Pi**, once available; record exact hardware, versions, timings and failures. | Lead/Sol runs the physical audio/HA/kiosk test, Codex login/isolation test and HA auth-callback test; set go/no-go thresholds before dependent runtime work. | Supported hardware candidate, Codex suitability and HA auth design are decided from evidence. |
| 3 | Port durable timers/alarms and deterministic light/list commands, then add a mock HA adapter. | Review state recovery, duplicate-action handling, validation and whether model text can reach mutations. | Unit/integration tests for restart, ambiguous writes, HA offline and repeated commands. |
| 4 | Port Pi Whisper/Piper/wake audio with a single microphone owner and push-to-talk fallback. | Review audio lease/cancellation, browser-crash behavior, acoustic re-trigger, license/provenance and ARM64 dependency reproducibility. | Physical test Pi measurements with HA/kiosk concurrent; no OOM; acceptable end-to-end voice behavior. |
| 5 | Implement the Codex answer adapter and fake-CLI harness from a Sol-approved isolation contract: structured output, timeout, cancellation, bounded history and distinct errors. | Threat-model process isolation, credential storage, config/plugin bypasses and prompt-to-shell paths before coding; inspect final diff and test results. | Signed-in and simulated failure tests; no access to HA secrets; measured latency and account limitations. |
| 6 | Build the first-run HA authorization/entity wizard, audio calibration, health dashboard, backup, rollback and setup checklist from a Sol-approved privileged-helper contract. | Review auth redirect, token lifetime/revocation, entity allowlist, helper permissions, install idempotency and failure recovery before coding and at final diff. | Fresh-owner setup without editing files or entering shell commands during normal onboarding. |
| 7 | Prepare release packaging, docs, redacted diagnostics and external beta feedback templates. | Final security/privacy/license review plus fresh-install, upgrade/restore and release-candidate diff review. | Independent fresh install, reboot, network loss, HA loss, mic loss, auth expiry, disk-full and interrupted-update checks. |

The lead agent owns scope decisions, integration conflicts, physical acceptance criteria and the publication decision. Sol High reviews after each security-sensitive boundary and again before every public merge/release. Luna Medium can handle parallel UI, test-fixture and installer work only after their shared contracts are fixed; agents must not edit the same files concurrently.

## First coding sprint

1. Publish only plan/safety documentation on a reviewed `codex/` branch. Resolve the owner's hardware and wake/voice defaults. Set proposed acceptance targets for voice latency, memory headroom, recovery and offline behavior.
2. While no separate test Pi exists, define stable interfaces for `HouseholdStore`, `HAClient`, `VoicePipeline`, `AnswerProvider`, health states, setup state and the privileged install helper. Build a clean skeleton, fake CLI and mock HA/audio harnesses with fictional fixtures. These are reviewable development artifacts, not evidence that the appliance works on Pi hardware.
3. Once a separately identified test Pi is available, run the three feasibility spikes: concurrent local audio/HA/kiosk performance; restricted Codex CLI login and answer calls; HA owner authorization callback. Record exact hardware/OS/package versions, timings and failure paths. A failed Codex gate returns to the owner for a backend decision; it does not silently switch to an API-key service. Keep runtime architecture and supported-hardware claims provisional until these gates pass.
4. Port local timers and command routing; then build the voice and onboarding paths in the work-package order above. Keep the current private installation running as-is throughout.

## Public posting sequence

- The remote repo is already public. First public push should be a **plan-only PR** from a fresh `codex/` branch based on its one-commit public history, labeled `pre-alpha`, with no copied private code, accounts, media or model weights. Keep `main` as a minimal honest project page until reviewed changes merge. A pushed branch and every commit on it are public immediately.
- Review the complete pushed commit range, not just the final working tree. Enable GitHub secret scanning and push protection, dependency alerts, and CI checks. GitHub's scanning supplements the manual allowlist and cannot prove that a household photo or private calendar name is safe.
- Subsequent PRs follow the work packages, each with a scope statement, test evidence, limitations and Sol review. Use a draft release for the first installable build, then a clearly labeled beta only after physical and fresh-owner acceptance. No “ready-made” claim until the wizard and recovery tests pass.
- Publish a README with supported hardware and OS versions, what stays local versus what goes to Codex, account requirements/limits, offline behavior, installation and uninstall, data handling, screenshots using fictional data, license notices, issue templates and a security reporting path. Avoid a general-purpose support promise for arbitrary microphones, screens and HA integrations.

## Open decisions and gates

- Owner: choose first supported Pi hardware and public wake/voice defaults; confirm whether calendar, weather and wake mode are required in the first beta or can follow the core timer/light/list/voice release.
- Define initial acceptance targets before benchmarking: exact Pi/RAM/OS/display/audio profile, maximum end-of-speech to local-action and first-spoken-answer times, sustained memory headroom, offline feature set, successful fresh install, and backup/restore behavior. If the Pi 4 candidate misses targets, revise the supported profile instead of hiding slow behavior.
- Feasibility: check the selected Pi's ARM64 package availability and concurrent latency/memory; Codex CLI startup, login/usage behavior and process isolation; HA auth redirect in the local kiosk.
- Legal/release: review exact voice/model licenses, copied-source ownership and whether GPL-3.0 remains appropriate before adding a license file or distributing assets. Choose a public support policy and versioning cadence after beta feedback.

## Source references checked for this plan

- Current private implementation was reviewed read-only outside this repository; no private paths or contents are part of the public source tree.
- Codex authentication and noninteractive mode: https://learn.chatgpt.com/docs/auth and https://learn.chatgpt.com/docs/non-interactive-mode (2026-09-22).
- Home Assistant auth and Pi container: https://developers.home-assistant.io/docs/auth_api/ and https://www.home-assistant.io/installation/raspberrypi-other/ (2026-09-22).
- GitHub security guidance: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-security-and-analysis-settings-for-your-repository (2026-09-22).
