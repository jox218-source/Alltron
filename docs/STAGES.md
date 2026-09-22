# Alltron stages and publication gates

Evidence date: 2026-09-22. This is the revised software-first plan. The existing private Pi and Home Assistant installation are outside every stage. Physical testing uses a separate device and occurs only after software and simulated acceptance are as complete as possible.

| Stage | Work and exit evidence | Current state |
| --- | --- | --- |
| **0. Public safety boundary** | Separate repository, no-reply Git identity, approved public paths, full-history privacy review before each push, fictional fixtures, license and security process. | In progress; repeat before every publication. |
| **1. Runnable foundation** | Local service and UI, setup and health states, durable timers, documented clean checkout, automated tests and CI. | Timer-only developer preview implemented; owner setup and broader contracts remain. |
| **2. Household core** | Deterministic commands, alarms, lists and an HA simulator. Test duplicate commands, restarts, offline states and ambiguous actions without hardware. | Planned. |
| **3. Home Assistant integration** | Reproducible HA Container packaging, owner account onboarding, local authorization, entity selection and selected-entity action allowlist. Test against disposable HA containers and synthetic households. | Planned. |
| **4. Codex answer boundary** | Restricted answer process, owner device login, bounded input/output, no HA credentials, timeouts and useful auth/limit/network errors. Test with a fake CLI and a disposable signed-in environment. | Planned; ARM64 behavior remains unverified until stage 7. |
| **5. Voice software** | One service-owned microphone path, local Whisper, wake/push-to-talk, Piper speech, mute and calibration. Use synthetic audio and test cancellation, recovery and asset provenance on development machines. | Planned; device timing and acoustic quality remain unverified until stage 7. |
| **6. Guided appliance build** | Idempotent installer, prerequisite checks, setup wizard, health dashboard, redacted diagnostics, backup, update, rollback and uninstall. Complete clean virtual-machine/container acceptance and outside-household usability trials where possible. | Planned. |
| **7. Dedicated Pi acceptance** | On a separate, clearly identified Pi, validate installation, HA/voice/Codex concurrency, ARM64 package support, latency, memory, microphone/speaker/display behavior, reboot, network loss, auth expiry, failed updates and recovery. Revise design and repeat until the supported profile passes. | Waiting for dedicated hardware; this is the last technical gate. |
| **8. Public beta** | Publish exact supported hardware/OS profile, limitations, release archive, license/asset notices and verified installation steps. Run independent fresh-owner trials on supported devices before calling it ready-made. | Blocked on stages 0–7. |

Software work may expose questions that require hardware evidence. Record those as explicit stage 7 acceptance risks and build replaceable adapters; do not quietly claim that mock or desktop tests prove Pi performance. No beta release or hardware-support claim precedes stage 7.

## Agent assignments and review

GPT-6 Luna Medium can take isolated, non-sensitive Alltron work: fictional fixtures, UI, docs, tests, CI and narrowly scoped modules after contracts are agreed. Same-host agents are **not isolated** from the private source by a worktree alone; sensitive implementation stays with the lead or a genuinely isolated OS/container environment. GPT-6 Sol High reviews security-sensitive contracts before implementation, then examines diffs, tests, dependency provenance and the complete public push range. The lead integrates work and records exact release evidence.

## Privacy gate before every GitHub push

1. Start from the public Alltron history. Never import the private project's history, source tree, symlink, state, recordings, photos, models, credentials or deployment targets. Review an explicit path allowlist.
2. Inspect **all new commits and Git objects**, including deleted files, binary assets and author/committer metadata. Run a secret scanner and manually check for names, addresses, device IDs, calendar data, media and personal configuration; `.gitignore` alone is insufficient.
3. If any questionable content entered a commit, rebuild from the clean public base before pushing. Removing it in a later commit does not remove exposure from public history.
4. Sol High reviews the exact SHA and final diff before a branch push. Use GitHub protection and scanning as additional controls, and verify release archives separately.
5. Keep every fixture invented and every support bundle redacted. Never publish account tokens, Codex auth state, real household data or current-Pi addresses.

The initial public GitHub commit predates this plan and contains a personal email in its Git metadata. The local Alltron development commit was rewritten to the chosen GitHub no-reply identity. Repository history already public cannot be made private by a later commit.
