# Security review and remaining gates

Evidence date: 2026-10-02. Alltron owner mode requires local password authentication and HTTPS; appliance acceptance remains open.
This review does not certify that the project has no vulnerabilities.

## Three review layers

1. **Publication and local inventory.** The publication auditor scans committed
   history and enforces literal public paths, regular text and approved identities.
   `python -m tools.credential_audit` also checks ignored files, credential/profile
   names, links, hardlinks, auth-shaped text and bounded ZIP members. Reports use
   categories/counts, never candidate values. Linux uses no-follow descriptors,
   verifies file identities and refuses nested mounts/cross-device traversal.
   Windows is a static inventory with identity checks, not an accepted adversarial
   filesystem boundary. Git objects and external credential stores need separate
   review. The tool never intentionally opens an external account profile.
2. **Application boundaries.** Fictional tests exercise private file reads,
   environment filtering, CLI output/time limits and cleanup, fixed HA services,
   redirect refusal and HTTP limits. No real account profile, token, household
   integration or Pi is used. Source archives use only committed allowlisted files.
3. **Independent review.** GPT-6 Sol High reviews code, full branch history,
   reachable/unreachable Git objects, licensing and the exact candidate SHA before
   pushing. GPT-6 Luna Medium writes fictional tests within the public-only boundary.
   The lead integrates fixes; the PR records exact evidence and approval.

## Changes in this slice

- HA config/token reads require absolute paths outside Git repositories, regular
  single-link files, no link/reparse ancestors and bounded UTF-8. Linux uses
  no-follow descriptor opens and owner-only file/parent permissions. Windows ACL
  enforcement remains unaccepted. Config is capped at 16 KiB, tokens at 4 KiB and
  aliases at 100. Invalid token bytes fail closed.
- Codex transport requires separate explicit work/profile/home directories,
  rejects repository/link paths and the developer's default profile, and strips
  inherited account/HA environment variables. Combined stdout/stderr is capped
  at 64 KiB with a 35-second deadline; errors expose no stderr. Linux cleanup kills
  the process group, including descendants retaining pipes. This is transport
  hardening, not an OS sandbox. Windows process-tree cleanup is unaccepted.
- HTTP caps concurrent handlers at eight, uses a three-second socket timeout and
  ten-second connection deadline, and rejects ambiguous framing, duplicate
  Host/Origin headers and unexpected action fields. Invalid JSON gets a generic
  response. Host/Origin checks provide browser request protection only.

## Deployment blockers

Resolve these before an appliance installer enables real integrations or a beta
claims hardened operation:

- Local API authentication is implemented with CLI enrollment, PBKDF2, bounded expiring sessions, secure cookies and session-bound CSRF. Fictional HTTPS tests pass. Clean-browser trust, certificate rotation and independent owner acceptance remain open. Explicit disconnected fixture mode remains unauthed and must contain only fictional data.
- HA now requires a pinned local certificate and verified HTTPS before token transmission. Owner-bound OAuth, refresh/revocation and explicit light/switch selection have fictional TLS tests. The lead reports a disposable Ubuntu 24.04 WSL2 trial at public revision `bf7b388` with verified TLS, fictional onboarding/OAuth callback exchange, synthetic device selection and virtual on/off, unknown-entity refusal, refresh expiry, and bounded outage behavior. The lead reports a revoke HTTP 200 followed by an HTTP 401 from the old trial credential. Home Assistant may return 200 for an unknown grant, so this result is trial-specific and the product correctly reports `requested-not-confirmed`; it is not general proof of remote revocation. Offline revoke failure retains local authorization. An explicit owner-only local disconnect removes Alltron's three local HA connection files without contacting HA. Fresh browser trust and certificate rotation remain open.
- Signed-in Codex is **disabled by `serve()`**. A lead reports all eight runner-boundary checks passed in WSL2: no network, read-only filesystem, non-root identity, and blocked host sentinels. This is not an independent VM or network-isolation acceptance, and no Codex login occurred. Establish and review a dedicated OS/container identity, isolated filesystem/credential store, network policy and resource limits, then perform a human-authorized sign-in/revocation trial in a disposable environment. Never
  copy or mount the developer's existing profile. `--ephemeral` prevents session
  rollout persistence; it does not remove login credentials. See OpenAI's
  [authentication](https://learn.chatgpt.com/docs/auth) and
  [non-interactive](https://learn.chatgpt.com/docs/non-interactive-mode) guides.
- At public revision `bf7b388`, the lead reports eight additional headless WSL2 lifecycle checks passed: activation refused; exact owned units uninstalled; database backup/mutate/restore; bad checksum rejected with code and DB unchanged; rollback to `b6c3ea7` preserved database, owner profile, HA keys, and auth state; repeat install/prepare/service-install preserved identity; services started after update; and uninstall removed only exact user units while preserving the three private storage roots. This was an implementer run, not an independent trial; no reboot test was run. Rootless Podman 4.9.3, systemd 255 user units, and service stop/restart recovery were also reported. Eight runner-boundary checks do not establish an independent network-isolated VM or Codex sign-in. A separate Windows rehearsal of the actual managed source archive passed install, run, lock, and application backup/restore. These remain partial observations; independent owner acceptance and service activation remain gated.
- A lead-reported Linux run before the final runner-boundary guard patch passed 130 tests and skipped 1; its exact source revision is not recorded. The final full-suite run is underway and the result is pending. Fresh browser trust, certificate rotation, general remote HA revocation/outage behavior, WSL reboot recovery, independent owner acceptance, speech asset review and dedicated-Pi acceptance remain open.

## Historical personal information

The original public commit and PR #1 merge retain the documented personal-email
Git metadata/message exposures in [PUBLICATION_GATE.md](PUBLICATION_GATE.md).
The owner previously chose to keep that history. This review does not erase
clones, caches or deleted remote objects, and does not claim historical metadata
contains no personal data. No new personal information is authorized for publication.

See the candidate PR for exact revision, scanner/test/archive results and Sol
approval. Rerun review after changes; scanner success is not production acceptance.

## Owner setup and service preparation

Local enrollment publishes a complete private TLS/password profile atomically. The owner UI guides HA OAuth and device selection; no HA password or token is passed through Alltron browser forms. Service preparation reuses verified committed archives, creates a separate private HA TLS profile and pins the official 2026.9.4 multiarchitecture image index. Generated user units constrain app filesystem/network/resources. Unit identity is checked before stopping/removing services. Activation is disabled until actual disposable runtime acceptance. No Codex credentials are imported, and the web service never instantiates the Codex transport. See [owner setup](OWNER_SETUP.md), [service procedure](LINUX_SERVICES.md), [acceptance checklist](SOFTWARE_ACCEPTANCE.md) and [speech provenance](SPEECH_PROVENANCE.md).

The lead reports that WSL2 lab additionally exercised synthetic HA on/off, unknown-entity refusal, refresh expiry, bounded offline behavior, and service stop/restart recovery. These are lead-reported, disposable observations; they do not establish real household control, independent-VM acceptance, or WSL reboot recovery. The reported service and runner checks do not open the activation gate. Remote revoke UI copy distinguishes a request from confirmed grant removal; local disconnect clears local files only, while offline remote-revoke failures retain them.
