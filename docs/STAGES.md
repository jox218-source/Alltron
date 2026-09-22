# Alltron stages and publication gates

Evidence date: 2026-09-22. This is a proposed schedule of work, not evidence that the appliance or any stage is complete. The existing private Pi and Home Assistant installation are outside every stage. No Alltron development branch has been pushed to GitHub as of this document.

## Stage 0 — Privacy wall and public project rules

Create Alltron only in its separate repository. Set an approved source-file manifest, fictional test data, a license decision, secret/file ignores, and a review checklist. Lead/Sol reviews any private-project source read-only; implementation agents receive an Alltron-only OS/container environment with no private mounts or credentials. No bulk copy, shared Git history, symlink or deployment target to the private project.

**Pass condition:** the complete local branch history and file tree contain only approved public material. Sol High signs off on the privacy boundary before the first push. This gate repeats for every later push.

## Stage 1 — Clean skeleton and simulated tests (can start now)

Define the Python service, local web UI, health states, setup state and contracts for timers, Home Assistant, voice and Codex answers. Add mock HA, fake CLI and synthetic audio fixtures. Luna Medium builds the non-sensitive scaffold and CI from the approved manifest; Sol High reviews interfaces and diffs. The current Pi is never used.

**Pass condition:** a clean checkout builds and tests without the private repository, real accounts or hardware. The UI and fixtures contain no real household names, photos, device IDs, addresses or calendar entries.

## Stage 2 — Dedicated Pi feasibility gate

After a separate test Pi is available, test local Whisper, speech synthesis, wake detection, Home Assistant Container and Chromium together. Test Codex CLI device login, isolated noninteractive answers, latency and account limits. Prototype HA owner authorization and its local callback. Record exact Pi/OS/audio hardware, memory headroom, response times and failures. A failed Codex or hardware gate returns to design review before dependent implementation.

**Pass condition:** Sol High accepts a measured supported-hardware profile, the Codex isolation/auth path, the HA authorization path and explicit performance targets. No public "ready-made" or hardware-support claim precedes this evidence.

## Stage 3 — Local household controls

Port durable timers and alarms, selected HA lights and to-do lists, and the deterministic command router. Keep HA actions bound to a user-selected entity/action allowlist. Luna Medium implements and tests; Sol High reviews duplicate actions, restart recovery, ambiguous writes and failure reporting.

**Pass condition:** touch and typed commands work with the PC off; timers recover after restart; unavailable HA never produces a false success message.

## Stage 4 — Pi voice pipeline

Implement one service-owned microphone path for push-to-talk, wake, utterance capture, Pi Whisper transcription and Pi speech playback. Provide mute and audio calibration. Luna Medium implements behind the approved contract; Sol High reviews microphone ownership, cancellation, wake retrigger and asset licenses.

**Pass condition:** spoken local controls work across browser refresh, service restart and ordinary room noise on the dedicated test Pi. Speech timing and memory remain within the agreed hardware profile.

## Stage 5 — Owner Codex answers

Implement a narrowly scoped answer adapter around the owner's Codex CLI login. The assistant sends bounded question text and returns an answer; it cannot directly mutate HA or access the household credential store. Give the Codex process a restricted OS identity, no private mounts, explicit timeout/cancel behavior and isolated configuration. Luna Medium implements the adapter/test harness; Sol High threat-models the boundary before coding and reviews final behavior.

**Pass condition:** login, logout/reconnect, ordinary answers, usage-limit, network-loss, timeout and cancellation cases are tested on the target Pi. No account credential appears in UI payloads, logs or support bundles.

## Stage 6 — Guided installation and recovery

Build a versioned installer, narrowly scoped privileged helper, first-run HA account/authorization flow, entity selection, audio checks, health dashboard, redacted diagnostics, backup and rollback. Luna Medium builds the wizard and recovery flows; Sol High reviews helper privileges, credential storage and update failure behavior.

**Pass condition:** a fresh owner can install and use core features without editing JSON or shell scripts during normal setup. A failed update restores the prior working release and saved household data.

## Stage 7 — Public beta and support

Run fresh-install trials with people outside this household using only the supported hardware list. Publish installation/uninstall docs, privacy/offline behavior, license and dependency notices, fictional screenshots, issue templates and a security reporting path. Post code through small `codex/` branch PRs; the first public PR is plan-only and labeled pre-alpha. A beta release follows physical acceptance and independent setup trials.

**Pass condition:** every pushed commit and release artifact passes the privacy gate below, and the README describes only capabilities verified on the supported profile.

## Privacy gate before **every** GitHub push

1. Start the branch from the public Alltron base; never import the private project's commit history or copy a whole source directory. Review an explicit allowlist of paths and assets. `.gitignore` is a backup check, not proof that ignored content cannot be added deliberately.
2. Inspect the **entire commit range and Git objects**, not only the final working tree. Review diff, file names, binary assets, generated artifacts, and Git author/committer names and email addresses. Run automated secret scanning locally before pushing; manually inspect names, addresses, calendar/device identifiers, audio, images, model weights and operational notes because generic scanners miss many of them.
3. Do not push a branch containing a questionable commit and then delete the file. A public branch exposes its earlier commits. Rebuild a clean branch from the public base if any private content ever entered its history.
4. Sol High reviews the final proposed push range and release archive. The lead records approval of the exact commit SHA to push. GitHub secret scanning/push protection should be enabled as an additional layer, not relied on as the first filter.
5. No credentials, pairing data, personal files, household media, real recordings, current-Pi addresses or private test results may be pushed. All screenshots and test fixtures use invented households and devices.

Current state: the local branch contains planning documents and the ignore rules only; no branch or PR was published in this task. The planning commit uses a GitHub no-reply author and committer identity. The original GitHub `main` commit predates this plan and its metadata must be considered separately. The dedicated test Pi is not yet available. Hardware choice, public wake word/voice defaults and first-beta feature scope remain open.
