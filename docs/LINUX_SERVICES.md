# Linux services

Evidence date: 2026-10-02. The Linux service command interface is implemented in [`tools/linux_install.py`](../tools/linux_install.py). A lead reports partial checks in a new checksum-verified Ubuntu 24.04 WSL2 lab; deployment and recovery remain unaccepted, and activation is deliberately refused. The current public source contains lifecycle changes after the tested commit noted below; no current-source full-suite result or independent owner trial is recorded. This document makes no general VM, clean-install, or hardware claim.

## Reported partial lab observations

On 2026-10-02, the lead reported verifying rootless Podman 4.9.3, systemd 255 user units, and successful user-unit starts in a new Ubuntu 24.04 WSL2 lab. The lab had Windows automount and interop disabled, shared mounts masked, and no user-private folders or profile copies. The report did not include private lab identity, paths, fingerprints, or credentials.

A separate lead-reported Linux run at public source commit `b6c3ea7` completed with 120 tests passed and 1 skipped. Later lifecycle changes are present in the current public source; this count is historical and must not be presented as the current suite result. The exact current public revision has no recorded full-suite result.

This evidence does not establish final service acceptance. The `activate` command still refuses service activation. No clean install/update/rollback rehearsal, independent owner trial, service restart/reboot recovery, or supported hardware profile is accepted here.

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

## Acceptance evidence still required

The lead reports a Linux run at `b6c3ea7` with 120 tests passed and 1 skipped, before subsequent service lifecycle changes in the current public source. This is not a current full-suite count, and no run result for the exact current source revision is recorded. The partial WSL2 checks above do not establish deployment acceptance. Rerun the full suite at an exact recorded public revision. Then rehearse preflight, prepare, service install/deactivate/uninstall, refused activation, managed update and rollback, backup/restore boundaries, state preservation, TLS, HA first boot and recovery in a disposable Linux environment. Follow with an independent owner trial. Keep the [software acceptance checklist](SOFTWARE_ACCEPTANCE.md) open until those results are recorded; keep the separate hardware gate open as well.

Home Assistant's 2026.8 release moved HTTP server settings into **Settings > System > Network** and migrates existing YAML settings on first startup after upgrade. Check the imported TLS values and follow the repair notice before the manual HA first boot/onboarding step. See [OWNER_SETUP.md](OWNER_SETUP.md), the [HTTP integration guide](https://www.home-assistant.io/integrations/http/), and [Home Assistant 2026.8 release notes](https://www.home-assistant.io/blog/2026/08/05/release-20268/).
