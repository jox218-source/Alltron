# Linux services

Evidence date: 2026-10-02. The Linux service command interface is implemented in [`tools/linux_install.py`](../tools/linux_install.py). A lead reports partial service and lifecycle checks in a new checksum-verified Ubuntu 24.04 WSL2 lab at public revision `bf7b388`; deployment acceptance remains open and activation is deliberately refused. The final full-suite run is underway and its result is pending; no independent owner trial is recorded. This document makes no general VM, clean-install, or hardware claim.

## Reported partial lab observations

On 2026-10-02, the lead reported verifying rootless Podman 4.9.3, systemd 255 user units, successful user-unit starts and stop/restart recovery in a new Ubuntu 24.04 WSL2 lab. The lab had Windows automount and interop disabled, shared mounts masked, and no user-private folders or profile copies. The lead also reports eight runner-boundary checks passing: no network, read-only filesystem, non-root identity, and blocked host sentinels. This does not establish WSL reboot behavior, a network-isolated independent VM, or Codex sign-in. The report did not include private lab identity, paths, fingerprints, or credentials.

The lead reports a disposable HA and service trial at public revision `bf7b388` covering verified TLS, fictional onboarding and OAuth callback exchange, device selection, virtual on/off, refusal of an unknown entity, refresh expiry, bounded offline failure, and service stop/restart recovery. Eight additional lifecycle checks reportedly passed: activation remained refused; exact owned service units were uninstalled; an existing Alltron database was backed up, mutated, and restored; a bad checksum was rejected without changing the selected code or database; code rollback to the earlier `b6c3ea7` archive preserved the application database, owner profile, HA keys, and auth state; repeat install, prepare, and service installation preserved identity; services started after update; and uninstall removed only the exact user units while preserving the three private storage roots. This was a headless implementer-run WSL2 trial, not independent acceptance. No reboot test was run.

A lead-reported 138-test run at public revision `f3c1cc9` was successful, with 13 skips on Windows and 1 skip on Linux. The run predates a UI health wording tweak and app-certificate rotation; the final current-source suite count is pending.

This evidence does not establish final service acceptance. The `activate` command still refuses service activation. The WSL2 lifecycle rehearsal does not replace an independent clean install/update/rollback trial, an independent owner trial, WSL reboot recovery, or supported hardware acceptance.

## Requirements

Use a supported Linux host, an ordinary Alltron owner account, and no `sudo` or root. The host must have Python 3.11+, OpenSSL, rootless Podman, and systemd user services. Verify rootless Podman actually works as that account (`podman info` without `sudo`) and that `systemctl --user` reaches the user's service manager; the command preflight reports platform/tool presence and is not a runtime acceptance test. Rootless Podman requires usable subordinate UID/GID mappings for the user. If automatic start after logout or reboot is needed, decide separately whether systemd user lingering is allowed.

Use disjoint, absolute paths outside the repository for the managed preview root, the private owner profile, and a dedicated Home Assistant data root. Keep the owner profile and HA data/certificate root private to the owner. The Alltron application unit uses the absolute Python executable passed to preparation and protects home directories; invoke preparation with the system interpreter at `/usr/bin/python3` (or the distribution's equivalent outside the owner's home), not a virtual-environment interpreter inside the home directory.

The service manager must already contain the exact trusted Alltron source archive through [managed preview installation](PREVIEW_INSTALL.md). It generates the Alltron unit's launcher from the current installed archive; it does not use an arbitrary working-tree path. The Home Assistant image reference compiled into the current installer is:

```text
ghcr.io/home-assistant/home-assistant@sha256:3e6710a7ab2a61311d9d899b719f6c3657791c63e8f4942cec4ebc42401d6b76
```

The lead verified this as the Home Assistant 2026.9.4 OCI image-index digest on 2026-10-02 with an anonymous registry request for the index; the index lists amd64 and arm64 manifests. See the official [2026.9.4 registry manifest endpoint](https://ghcr.io/v2/home-assistant/home-assistant/manifests/2026.9.4) and [Home Assistant Container image package](https://github.com/home-assistant/core/pkgs/container/home-assistant/versions). The source archive contains only this image reference; it does not contain the OCI image or speech model weights. Preparation does not pull the image, and the generated HA unit uses `--pull=never`; a verified image must exist in the owner's rootless Podman store before that unit can run. Activation remains refused, so do not start it manually.

## Preflight and preparation

Run these commands from the exact reviewed Alltron source archive that has been installed into the managed preview root. Pass the profile directory, not `owner.json`, to the Linux service tool.

```sh
/usr/bin/python3 -m tools.linux_install preflight
/usr/bin/python3 -m tools.linux_install prepare \
  --root /absolute/private/alltron-managed \
  --profile /absolute/private/alltron-profile \
  --ha-root /absolute/private/alltron-ha
```

`preflight` reports platform and executable presence plus `live_acceptance: false`; it does not establish that rootless Podman or a user systemd manager works. `prepare` requires the current managed source archive, a valid owner profile, OpenSSL, Podman, and systemd executables. It rejects overlapping paths and requires an existing HA root to be owner-private and either empty or marked as the matching Alltron HA profile.

On first preparation, it atomically creates a dedicated HA TLS profile under `--ha-root`, including a certificate, private key, TLS configuration, and image/port marker. It copies the public HA certificate into the owner profile's trust file and configures the verified loopback endpoint. It writes the two owner-private service unit files and service metadata into the owner profile using private, atomic file writes. It returns the app and HA certificate SHA-256 fingerprints, the selected source version, the pinned image reference, and `services_started: false`. Verify the fingerprints through the trusted local setup output before trusting the generated certificates. `prepare` does not start, enable, install, or pull either service/image.

Preparation creates and preserves the HA certificate identity. Repeating it with a mismatched image/port marker fails instead of overwriting that identity. Existing HA configuration and state are not replaced. Do not point `--ha-root` at another Home Assistant installation or household data.

## Explicit service commands

Each command below takes `--profile` as the owner profile directory:

```sh
/usr/bin/python3 -m tools.linux_install install-services --profile /absolute/private/alltron-profile
/usr/bin/python3 -m tools.linux_install activate --profile /absolute/private/alltron-profile
/usr/bin/python3 -m tools.linux_install deactivate --profile /absolute/private/alltron-profile
/usr/bin/python3 -m tools.linux_install uninstall-services --profile /absolute/private/alltron-profile
```

- `install-services` copies only the reviewed `alltron.service` and `alltron-ha.service` from the owner profile into `~/.config/systemd/user/`, then reloads the user manager. It does not start or enable them.
- `activate` is implemented as an explicit command but always refuses while disposable service and container acceptance is pending. Do not work around that refusal with direct `systemctl` or Podman commands.
- `deactivate` checks that both installed unit files exactly match this profile's generated units before it asks systemd to disable and stop them. If either unit is missing or changed, it stops and preserves the files for review.
- `uninstall-services` deactivates both exact units, removes only unit files that still match the profile, and reloads the user manager. It preserves the managed application root, application data, owner profile, HA TLS/configuration/data root, and Home Assistant grant.

Codex remains disabled. The service unit bounds the App process and gives it loopback network access only; the HA container unit is separate. These source settings are design/implementation evidence, not proof of isolation, service reliability, least privilege, or hardware support.

## Updating, rollback, and state

Before an archive update, code rollback, or application backup/restore, both installed services must be stopped. When the service units are installed, first run `uninstall-services` with the existing owner profile; that operation validates the exact generated units, disables and stops them, then removes the matching unit files. If it fails, stop and investigate before changing the archive or state.

After the stop:

1. Use the managed preview archive tool to install the reviewed exact archive or select the prior code with its rollback command. The managed tool preserves application data separately from release code.
2. Run `prepare` again from the new selected archive with the same owner profile and dedicated HA root. This refreshes private units and records the current code version; it does not start the services.
3. Run `install-services` to copy the newly prepared units into the user manager. This only installs/reloads units. Activation remains blocked pending acceptance.

The preview [backup and restore tool](PREVIEW_BACKUP.md) covers the Alltron SQLite application database only. It does not include the owner profile, local owner credentials/certificates, HA access/refresh credentials, HA configuration, or Home Assistant data. Preserve those private paths with a separate reviewed backup process. This installer does not provide HA backup/recovery or HA data migration.

### Rotating the Alltron HTTPS certificate

Stop service units first using `uninstall-services` with the existing owner profile, as described above. With the same reviewed Alltron release's Python environment, run `python -m alltron.setup --profile /absolute/private/alltron-profile --rotate-certificate`; the command is restricted to an ordinary Linux owner and serializes changes with the profile setup lock. It generates and validates a new app TLS pair in a private generation directory, then atomically updates the `owner.json` pointer. The password hash and old TLS files are preserved, and active web sessions are revoked. After rotation, query `--certificate-info` to print the active path and SHA-256 fingerprint, then compare that fingerprint with the certificate presented by the browser and trust only the new identity. Trust-store changes are manual; this CLI does not alter the browser or OS trust store.

Run `prepare` and `install-services` again with the same managed root, owner profile and HA data root. Service activation remains refused pending acceptance. This rotates only the Alltron app certificate; the HA certificate and its trust configuration are unchanged. Home Assistant certificate rotation has not been accepted. See [owner setup](OWNER_SETUP.md) for the owner commands and browser identity check.

## Acceptance evidence still required

The lead reports a 138-test run at public revision `f3c1cc9`, with 13 skips on Windows and 1 skip on Linux; the other tests passed in those runs. This revision predates a UI health wording tweak and certificate rotation, so it is not the final current-source result. The final suite count is pending. The partial WSL2 checks above do not establish deployment acceptance. Review the exact final test result, then complete the independent owner trial, WSL reboot check, and remaining TLS, HA recovery, and Codex gates. Keep the [software acceptance checklist](SOFTWARE_ACCEPTANCE.md) open until those results are recorded; keep the separate hardware gate open as well.

Home Assistant's 2026.8 release moved HTTP server settings into **Settings > System > Network** and migrates existing YAML settings on first startup after upgrade. Check the imported TLS values and follow the repair notice before the manual HA first boot/onboarding step. See [OWNER_SETUP.md](OWNER_SETUP.md), the [HTTP integration guide](https://www.home-assistant.io/integrations/http/), and [Home Assistant 2026.8 release notes](https://www.home-assistant.io/blog/2026/08/05/release-20268/).
