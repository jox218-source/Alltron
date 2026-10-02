# Local owner setup

Evidence date: 2026-10-02. This guide documents the early Linux owner setup and Home Assistant authorization flow. It has not passed an independent fresh-owner VM trial or separate-Pi acceptance. Alltron remains pre-alpha; the steps below do not establish appliance readiness or supported hardware.

## Create the local owner profile

Use an ordinary Linux user account, not `root` or `sudo`. Install Alltron in a Python 3.11+ virtual environment. Choose a dedicated absolute profile directory outside the repository and any shared or synchronized folder. Its parent must be private to your Linux user; setup creates the profile with owner-only permissions. Keep the profile, `owner.json`, certificate, private key, and application data private and backed up securely.

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -m alltron.setup --profile /absolute/private/profile
```

The setup command asks for a local Alltron password twice without echoing it. Choose at least 12 characters. The password stays in the local terminal; never put it in a command argument, URL, browser query, shell history, issue, or support bundle. Setup creates `/absolute/private/profile/owner.json` and the Alltron HTTPS certificate/key. It requires local OpenSSL and an empty or already-complete owner-only profile; it stops rather than overwriting an incomplete profile.

Start Alltron in owner mode:

```sh
alltron --owner-profile /absolute/private/profile/owner.json
```

Open the exact `https://127.0.0.1:<port>` URL printed by the process, on the same device. The default port is `8765`; keep the service bound to loopback. The browser login uses the local Alltron password. Before entering it, inspect the browser's HTTPS certificate and compare its SHA-256 fingerprint with the generated profile certificate:

```sh
openssl x509 -in /absolute/private/profile/alltron.crt -noout -fingerprint -sha256
```

Trust only that generated certificate after the fingerprint matches exactly. Use the browser or operating system's certificate trust controls for that certificate. If the fingerprint differs, the certificate is missing, or the browser cannot establish the expected identity, stop and resolve the discrepancy. Do not bypass a certificate warning blindly or accept a different identity to continue.

## Authorize Home Assistant

Create the Home Assistant owner account through Home Assistant's own first-run flow. Do not enter the Home Assistant password, access token, or refresh token into Alltron. The Alltron UI sends you to Home Assistant's authorization page; approve only the request you intentionally started. On return, load the available devices, select only devices Alltron may control, assign a unique short spoken name to each, and save. Use **Revoke Home Assistant access** to remove the saved authorization and selection.

Alltron requires Home Assistant at a local HTTPS endpoint whose certificate identity it verifies. Do not authorize over plain HTTP or continue if certificate verification fails. Home Assistant's current HTTP server page documents TLS certificate and key settings under **Settings > System > Network**. Home Assistant 2026.8 moved HTTP server configuration from YAML into that UI; an existing YAML `http:` block is imported at first startup after upgrading, and a repair notice may ask you to remove the old block after checking the imported settings. For Home Assistant Container, the default HTTP port remains `8123`; Home Assistant OS defaults to port `80` starting in 2026.8. Confirm the actual local port and TLS settings for your installation before authorizing. See the [Home Assistant HTTP documentation](https://www.home-assistant.io/integrations/http/) and [2026.8 release notes](https://www.home-assistant.io/blog/2026/08/05/release-20268/), checked 2026-10-02.

The owner UI accepts only an authorization URL using HTTPS on hostname `127.0.0.1`; Alltron's local service also verifies the configured Home Assistant certificate before sending authorization. If endpoint TLS trust is not provisioned or verification fails, stop. No warning bypass or manual credential fallback is provided by this flow.

The local Alltron password is verified by the local Alltron service. Home Assistant OAuth access and refresh credentials are stored server-side in the private owner profile; the browser UI does not receive or store them. Codex answers remain disabled pending isolation acceptance.

### Revocation and local disconnect

**Revoke Home Assistant access** asks Home Assistant to revoke the saved authorization and then removes Alltron's local authorization files when that remote request succeeds. If Home Assistant is offline, its certificate cannot be verified, or the remote revoke request fails, Alltron must retain the local authorization files because remote revocation was not confirmed. Restore the verified Home Assistant endpoint and retry revocation. Do not assume a failed request revoked access.

There is currently no separate local-only disconnect button or command. Stopping Alltron prevents this process from using the saved authorization while stopped, but does not revoke Home Assistant's grant or remove the saved credentials. Do not delete profile files manually as a substitute for confirmed revocation.

## Preview mode and unavailable features

The normal owner mode uses HTTPS and an owner profile. `--fixture-preview` is a disconnected fictional-data mode for development only. It requires an explicit disposable `ALLTRON_DATA_DIR`, serves HTTP, and must not be used for a real owner, Home Assistant account, household data, or credentials. It is not a way around owner login or certificate verification.

Codex answers are disabled pending isolation acceptance. Speech readiness is not evidence of a successful spoken test. No Pi model, microphone, speaker, wake path, latency, or hardware profile has passed acceptance. See [software acceptance](SOFTWARE_ACCEPTANCE.md), [speech provenance](SPEECH_PROVENANCE.md), and the [developer preview installation guide](INSTALL.md) for current limits and required evidence.
