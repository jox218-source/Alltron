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
- HA now requires a pinned local certificate and verified HTTPS before token transmission. Owner-bound OAuth, refresh/revocation and explicit light/switch selection have fictional TLS tests; native HA Container onboarding, token authority and outages still require live disposable acceptance.
- Signed-in Codex is **disabled by `serve()`**. Establish a dedicated OS/container
  identity, isolated filesystem/credential store, network policy and resource
  limits, then accept owner sign-in/revocation in a disposable environment. Never
  copy or mount the developer's existing profile. `--ephemeral` prevents session
  rollout persistence; it does not remove login credentials. See OpenAI's
  [authentication](https://learn.chatgpt.com/docs/auth) and
  [non-interactive](https://learn.chatgpt.com/docs/non-interactive-mode) guides.
- Live disposable HA, fresh-owner setup, Linux service installation, speech asset
  review and dedicated-Pi acceptance remain pending. The existing Docker Linux engine was unavailable. A separate clean Linux lab is being prepared; its outcomes must be recorded separately. Unit tests are not signed-in acceptance evidence.

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
