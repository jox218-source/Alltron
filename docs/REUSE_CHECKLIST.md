# Public reuse checklist

Evidence date: 2026-09-26. This is a sanitized feature and test checklist for Alltron. It records public implementation targets informed by read-only reviews of separate private speech and full-release previews. It contains no private source, configuration, recordings, model assets or device details.

| Area | Alltron contract | Acceptance evidence |
| --- | --- | --- |
| Timers and alarms | Store deadlines durably; cancel by opaque ID; report completed versus running state; do not claim an alarm sounded merely because its deadline passed. | Restart, duplicate request, missed-deadline and cancellation tests. |
| Local commands | Parse a small explicit set of household commands into typed intents; validate parameters before any action; return an unavailable or ambiguous result instead of guessing. | Fictional command fixtures and denied/ambiguous action tests. |
| Lists | Store local list items with stable IDs and completion state. Do not infer an item from a partial or ambiguous name. | Add, duplicate, complete, restart and nonexistent-ID tests. |
| Voice state | Report wake, speech recognition and speech output independently, each as `ready`, `disabled` or `unavailable`; keep request IDs and cancellation. | State transition, interrupted request, engine failure and service restart tests. |
| Audio ownership | One service process owns the selected microphone stream for wake and utterance capture; browser refresh never transfers ownership. Speech playback pauses wake processing. | Fake capture stream tests, then normal-volume acoustic tests on a separate Pi. |
| Speech engines | Resolve pinned upstream Whisper and Piper dependencies separately from app code and select models with recorded provenance. No engine or voice asset is included in this repository by default. | Dependency/license inventory, direct-worker spoken smoke, full-path spoken smoke and physical latency measurements. |
| Home Assistant | Owner account and authorization, selected entity/action allowlist, verified state after writes. | Disposable HA tests; no real household identifiers in fixtures. |
| General answers | Owner Codex CLI login in a restricted process; output is text only and cannot authorize a household action. | Fake CLI failure tests and disposable signed-in trial. |
| Release artifact | Build from an explicit public file allowlist; record per-file hashes and a versioned release identity; leave secrets, state, models and personal media outside the archive. | Deterministic rebuild, inventory/hash audit, source-license review and rejected unapproved-path fixtures. |
| Setup and recovery | Selected input/output devices, redacted status, repeatable install, backup, rollback and uninstall. | Clean disposable install and independent fresh-owner trial before beta. |

The existing Alltron preview is the only application code reused directly. The private previews provide behavior and failure-mode evidence only. Public code is authored in Alltron; third-party source and model licenses are checked before distribution. A separate, allowlisted Pi is required before any supported-hardware or ready-made claim.

Open [PR #9](https://github.com/jox218-source/Alltron/pull/9) includes a deterministic source ZIP, exact path allowlist, per-file hashes, local preview staging/code rollback and application database backup/restore. These slices have synthetic and disposable local tests. They do not install a Pi appliance or HA, migrate data, guide an owner through setup or constitute release approval. The private preview's time-zone-sensitive Windows result remains a separate observation; it is not Alltron acceptance evidence.
