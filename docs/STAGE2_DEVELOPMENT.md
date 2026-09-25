# Stage 2 owner integrations

Evidence date: 2026-09-25. This page records the first software implementation and remaining acceptance work for Home Assistant (HA) and Codex CLI integrations. Fake HA and CLI tests pass locally. No live HA or signed-in Codex integration has been accepted. Examples and entity names are fictional.

## Scope and boundary

Stage 2 connects owner-authorized integrations to the deterministic Stage 1 router. It does not give an LLM authority to choose or invoke HA actions. HA and Codex are separate adapters with separate credentials and failure handling. The browser receives neither credential. Use a disposable Linux test environment and synthetic devices; never use the existing household HA installation or a personal Pi as a development target.

The two tracks can begin independently:

1. HA: exercise authorization, a narrow alias-to-entity allowlist, and permitted light/switch services against disposable Home Assistant Container.
2. Codex CLI: define and exercise an injectable fake-runner contract, then establish whether the CLI can run safely inside a disposable OS/container boundary before any real signed-in enablement.

## Track A: disposable Home Assistant

### Test environment

- Use a disposable Linux VM or isolated Linux host and a throwaway Home Assistant Container instance. `dev/ha-compose.yaml` binds only to host loopback and mounts a caller-supplied disposable configuration directory outside the repo. It is for API software tests; device discovery and hardware integrations are not configured. Pin and record the image version for each acceptance run. Do not connect real integrations or import a backup.
- Create synthetic entities such as `light.test_lamp` and `switch.test_fan`; keep the instance on an isolated test network. Verify status and actions only against those entities.
- Record the OS, container runtime, Home Assistant version, configuration and test result. Remove the test instance and its data when the run is complete.

### Initial authorization approach

For the first prototype, the owner creates a Home Assistant long-lived access token from the test user's profile and supplies it locally during setup. Home Assistant documents this token flow for API requests using `Authorization: Bearer …` ([REST API](https://developers.home-assistant.io/docs/api/rest/), [authentication API](https://developers.home-assistant.io/docs/auth_api/)). This is a prototype choice, not the final authorization design. HA documents long-lived access tokens as valid for ten years; treat the token as a broad, sensitive credential and revoke it after testing. Do not print it, put it in a URL, commit it, include it in logs/support bundles, or paste it into a prompt.

For development, provide the token through a test-only secret file outside the repository, with owner-only filesystem permissions. `ALLTRON_HA_CONFIG` points to a separate private JSON file containing an absolute `token_file` path, a numeric loopback `port`, and an `aliases` object. The two files require mode 600 on POSIX. No token is accepted through the browser. Keep the file out of Docker build contexts, source control, backups used as fixtures, and published artifacts. Production credential provisioning, storage, rotation, revocation UX and a narrower authorization option remain open gates; do not treat a local token file as a finished installer design.

### Alias and action policy

Require an explicit owner-reviewed map from human-readable aliases to exact entity IDs and allowed operations. For example:

```json
{
  "port": 8123,
  "token_file": "/outside-the-repo/alltron-test/owner-token",
  "aliases": {
    "desk lamp": "light.test_lamp",
    "test fan": "switch.test_fan"
  }
}
```

This is the current prototype schema. The router resolves an alias only through this map. The initial scope is `light.turn_on`, `light.turn_off`, `switch.turn_on` and `switch.turn_off`; all other domains and service payloads are unavailable. Do not accept an arbitrary entity ID or service call from UI text, a transcription, a Codex answer or an API caller. Do not add scenes, scripts, locks, covers, climate controls, groups, templates or broad `call_service` passthrough in Stage 2.

The allowlist must be enforced in the local router immediately before the HA request, not only in the UI. Reject unknown aliases and malformed or extra fields without making a request. Responses and logs should identify the fictional alias and outcome, not include tokens or unfiltered HA payloads.

### HA software acceptance gates

- Missing, unreadable, malformed, expired and revoked token cases fail closed with a useful local setup/status error; secrets do not appear in logs, API responses or support output.
- The adapter reads only the minimum state needed for selected aliases and invokes only the four permitted on/off operations against synthetic entities. The token inherits the test user's authority, so the disposable instance and test account must contain no real integrations or household data.
- Unknown aliases, entity IDs supplied directly, domain mismatch, forbidden service, extra service data and malformed requests are rejected before network dispatch.
- HA unavailable, timeout, authorization failure, unexpected response and retry cases preserve clear request outcomes and do not silently repeat state-changing calls.
- Restart the Alltron service and the disposable HA container; confirm configuration reference and behavior remain predictable without exposing the token.
- Revoke the test token and verify subsequent requests fail closed. Destroy the disposable instance and remove the test secret.

Passing these software checks is not acceptance of real household devices, final credential UX, or a supported installation.

## Track B: Codex CLI answer adapter

### Fake-runner contract

The implemented adapter uses an injected runner so tests use a fake executable and no account credentials. It accepts one bounded plain-text question after local routing has classified it as a general question. The CLI transport uses fixed arguments, stdin, a 35-second timeout and a fixed instruction to answer concisely without tools or actions. It does not use a shell or interpolate question text into a command. The displayed reply is capped at 2,000 characters; a hard process-output memory cap remains to be added before production enablement. It does not pass HA credentials, audio, entity state, household files, project paths or ambient conversation history by design, but this must be verified in an isolated runner trial.

The fake runner should support deterministic fixtures for a normal answer, empty output, malformed output, oversized output, timeout, non-zero exit, unavailable executable and interrupted request. Tests should verify the exact input and arguments, output bounds, timeout/cancellation, error mapping, and that a failed or refused answer cannot become an HA action. Fake runs must not inspect or create a real Codex profile.

The adapter should expose a narrow result such as `answer`, `unavailable`, `timed_out`, `rejected` or `failed`, with bounded display text and a redacted diagnostic category. It must not expose raw environment data, process environment variables, credential-store contents, arbitrary stderr or filesystem paths to the UI. Network use, account limits, billing or usage behavior, retention, and provider processing must be explained before an owner enables signed-in answers.

### Isolation gate before signed-in enablement

Codex CLI sign-in stores credentials locally according to OpenAI's [authentication guide](https://learn.chatgpt.com/docs/auth). The guide describes `codex login --device-auth` for headless devices; the [non-interactive guide](https://learn.chatgpt.com/docs/non-interactive-mode) describes `codex exec`, `--ephemeral`, and read-only sandboxing. No real signed-in CLI test or owner enablement may occur until the runner has been assessed and tested inside a genuine OS or container security boundary. A separate directory, worktree, process, Python environment, or user-visible prompt alone is not sufficient isolation. The present CLI transport is intentionally not wired by `serve()`.

The disposable signed-in trial must use a dedicated temporary profile and a disposable Linux VM or container with:

- a dedicated unprivileged identity, no elevated capabilities, and no host home-directory, repository, household-file, microphone, device, Docker socket or HA-token mounts;
- only a temporary writable profile and narrowly scoped temporary input/output locations, with restrictive permissions and cleanup after the run;
- resource, process, time and output limits, explicit network policy, and no background daemon or unattended follow-up execution;
- only the bounded question text as input, with no direct path to invoke Alltron tools or HA; and
- documented sign-in, sign-out/revocation, token/profile cleanup, network/provider data flow, and failure behavior.

Test in that boundary only with fictional prompts and confirm that attempts to access host files, environment secrets, HA, or disallowed network destinations fail. Inspect the exact process arguments, environment, mounts, permissions, logs and cleanup. Establish whether Codex CLI works reliably under those restrictions and on the intended Linux/ARM64 profile. If an enforceable boundary or reliable restricted operation cannot be demonstrated, keep signed-in answers disabled and record the unresolved reason; fake-runner completion does not waive this gate.

## Integration gates and unresolved decisions

Both tracks must meet these conditions before Stage 2 is considered complete:

- The Stage 1 router sends deterministic supported commands to HA and general questions to the answer adapter; ambiguous, unsupported or unsafe input is rejected or clarified.
- No Codex output can authorize an HA action, change the alias allowlist, or trigger another command.
- Startup health distinguishes disabled, unconfigured, ready and failed integrations without disclosing secrets. Timeouts, service outages, auth failures, rate/usage limits and cancellation return bounded user-facing status.
- Logs and support bundles are redacted and bounded. No audio is sent to either integration by this Stage 2 contract.
- A disposable Linux setup can configure, exercise, revoke and remove both test integrations without personal data or credentials entering the repository.
- Security review covers the HA token's authority and storage, command construction, process isolation, network access, output handling and provider data flow. Record exact versions and evidence; do not describe a proposed control as verified until exercised.

Open decisions for later review include a supported HA authorization/credential lifecycle beyond the prototype token file; least-privilege options and user/account model; final allowlist configuration UX; Codex CLI support and account terms on the target OS/architecture; isolation mechanism and network policy; answer retention and provider disclosure; and whether signed-in answers should ship enabled, opt-in or unavailable. Resolve these before Stage 3 setup UX or a public beta claims the feature is supported.

## Evidence and publication note

The synthetic adapter tests are implementation evidence only, not acceptance of a real integration. Track disposable Linux test results, versions, defects and decisions when work occurs. The publication allowlist must include every new file before this page or the implementation can be pushed.
