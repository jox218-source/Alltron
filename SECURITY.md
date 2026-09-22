# Security policy

## Project status

Alltron is pre-alpha. It has not completed a security review and should not be treated as a hardened or safety-certified product. Do not expose its control interface to the public internet or use it for safety-critical functions.

The current timer preview assumes a trusted, single-user computer. Its loopback API has no account authentication; other local users or processes on a shared computer may be able to reach it. Use a dedicated account/device and avoid sensitive timer labels until local authorization is implemented.

## Supported versions

No stable release is currently designated. Security fixes will be made on the active development branch while the project is pre-alpha. Once supported releases exist, this section will list their version ranges.

## Reporting a vulnerability

Please do not disclose vulnerabilities in public issues, discussions, or pull requests. Use GitHub's **[Report a vulnerability](https://github.com/jox218-source/Alltron/security/advisories/new)** option to send a private advisory to maintainers. Private vulnerability reporting was verified enabled on 2026-09-22. If GitHub makes that option unavailable, do not post exploit details publicly; contact the repository owner through GitHub with only a minimal request for a private reporting route.

Include the affected revision, impact, reproduction steps using a fictional or isolated environment, and any suggested mitigation. Redact tokens, hostnames, IP addresses, entity names, and personal data. Please allow maintainers reasonable time to investigate and coordinate a fix before public disclosure.

## Security expectations

- Store credentials only in local, ignored configuration or the operating system's secret store; never in source control or logs.
- Grant Home Assistant only the access needed for the configured features.
- Treat transcripts, audio, entity names, prompts, and CLI output as sensitive household data.
- Keep control interfaces on a trusted local network and document any listening address or firewall change.
- Validate commands and service targets before actions reach Home Assistant. Never treat model output as executable shell input.
- Report whether an issue requires physical access, local network access, account access, or user interaction.
