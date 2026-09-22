# Alltron software-first build and release plan

Evidence date: 2026-09-22. This plan describes proposed work and gates. The runnable local timer preview is the only implemented app capability so far. No Alltron software has been deployed to a Pi or verified as an appliance.

## Decisions

- Alltron lives in the separate public `jox218-source/Alltron` repository. Work on reviewable `codex/` branches. Never import the private project's Git history, source tree, household state or current-Pi connection details.
- The intended appliance installs Home Assistant Container on the same Pi. Each owner creates their own HA account and signs in to Codex CLI for optional general answers. The public edition omits personal-file search, PC gateway and local language-model serving.
- Keep a locally served touchscreen UI with a Python service. The service owns microphone capture, local Whisper transcription and speech playback; browser refresh must not interrupt the voice session.
- Finish the software build, simulated integrations, guided installer and desktop/VM acceptance before purchasing or using a dedicated test Pi. The Pi is the final technical validation gate before beta; software acceptance is not evidence of Pi latency or hardware support.
- The public code uses GPL-3.0-only. Review every bundled engine, model, voice, wake asset and copied component separately before distribution.

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

The browser handles touch and setup. Household mutations pass through a local, typed command router and owner-selected entity/action allowlist. The answer adapter receives bounded question text and cannot directly reach HA actions or credentials. It runs under a restricted OS identity with isolated configuration, empty working directory, timeouts and no plugins/MCP integrations. Codex CLI is a coding-agent interface; suitability and isolation must be tested before enabling it by default on a Pi. Account or usage restrictions may make it unavailable for some owners. No general-answer text is executed as a household command.

The ordinary API must not run as root or receive the Docker socket. A minimal privileged installer helper may perform only named install/update/rollback operations after validating caller, paths, versions and verified artifacts. The HA token stays server-side with restrictive permissions and revocation support. The owner uses HA's account onboarding and authorization flow; the UI must never ask for an HA password. A manual token may be a labeled development fallback only.

## Work allocation

| Stage | GPT-6 Luna Medium implementation | GPT-6 Sol High review | Evidence to leave behind |
| --- | --- | --- | --- |
| 0–1: safety and foundation | Public UI, fictional fixtures, docs, CI and small modules after contract approval. | Privacy boundary, entire branch history, API surface and test quality. | Clean checkout, runnable preview, test output and exact reviewed SHA. |
| 2: household core | Durable alarms/lists, typed commands and mock HA under approved interfaces. | Recovery, idempotency, ambiguous writes and false-success prevention. | Unit/integration tests for restart and unavailable services. |
| 3: HA | Disposable HA test harness, authorization UI and entity selection after contract review. | Auth callback, token handling, allowlist and denied-action behavior. | Synthetic fresh-owner flow; HA loss and reauthorization tests. |
| 4: Codex | Fake CLI harness and adapter after isolation contract review. | Threat model, account state, config/plugin bypass, prompt-to-shell paths and failure messages. | Timeout, cancellation, limit, network and auth tests; no secret in logs. |
| 5: voice | Synthetic audio harness, pipeline and calibration UI after contract review. | Microphone ownership, cancellation, retrigger, dependency and asset provenance. | Desktop/VM tests; explicit unverified Pi performance. |
| 6: appliance | Wizard, preflight, installer, diagnostics, backup and rollback after helper contract review. | Helper privileges, idempotency, recovery and privacy of support bundles. | Simulated fresh install, upgrade, failure and restore tests. |
| 7–8: physical gate and beta | Package fixes and docs from dedicated-Pi findings; release prep. | Final hardware, security, privacy, license, archive and release-candidate review. | Exact supported profile, measurements and independent owner setup results. |

The lead fixes contracts, integrates scoped work and owns physical acceptance and publication decisions. Agents do not edit the same files concurrently. Every public push repeats the privacy gate in [STAGES.md](STAGES.md).

## Foolproof owner experience to reach before beta

1. A versioned, checksum-verified release checks Pi model/RAM, OS, free storage, audio/display devices, network and Docker availability and gives a plain-language remedy for failures.
2. Installer performs idempotent named steps and offers uninstall/rollback. A failed update restores the prior working release and saved household state.
3. First-run wizard starts HA, hands account creation to HA, completes owner authorization, selects controllable entities and tests an action. It then handles Codex login under the restricted identity and verifies a harmless answer. No credential is pasted into a public issue or stored in the browser.
4. Audio check shows input level, output test, mute state and push-to-talk fallback. Setup cannot mark voice complete if its device or models are missing.
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
