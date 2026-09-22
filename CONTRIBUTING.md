# Contributing to Alltron

Thanks for helping make Alltron easier to install and operate. Alltron is in pre-alpha: interfaces, supported hardware, installation steps, and security controls can change. Check the current README and roadmap before starting work, and describe uncertainty plainly.

## Before you start

1. Search existing issues and pull requests to avoid duplicate work.
2. For a large change, open an issue first and agree on the expected behavior.
3. Keep changes focused. Do not include credentials, household information, device exports, audio recordings, private configuration, or files copied from another installation.
4. Use fictional examples and test fixtures. Never target a real Home Assistant instance or Raspberry Pi in automated tests.

## Local development

The project is not yet at a stable developer setup. Follow the README's current setup instructions. If a step is missing or fails, report the exact command, operating system, Python/runtime versions, and a redacted error excerpt. Do not paste tokens, local IP addresses, usernames, or full environment dumps.

Before submitting, run the checks documented for the area you changed. Maintainers run the [publication privacy gate](docs/PUBLICATION_GATE.md) on the exact commit before each push; contributors should use a GitHub no-reply commit identity and avoid adding paths outside the reviewed manifest. If no automated behavior check exists, say so in the pull request and include a concise manual verification procedure. Do not claim Raspberry Pi verification unless it was performed on a dedicated test device and the model, OS, and result are recorded without identifying the device or network.

## Pull requests

Use a short, descriptive title and explain:

- the problem and the behavior changed;
- setup or migration impact;
- checks run and their results;
- remaining limitations and hardware tested, if any;
- any new permissions, network access, stored data, or external services.

Keep documentation accurate to the current implementation. Add or update tests for behavior changes when an appropriate test harness exists. Do not commit generated build output, secrets, personal paths, or unrelated formatting changes.

## Security and privacy

Do not report vulnerabilities in public issues. Read [SECURITY.md](SECURITY.md) for the current reporting route. Treat logs, audio, Home Assistant entity names, and CLI output as potentially sensitive. All examples must use fictional values such as `192.0.2.10`, `example.invalid`, and `REDACTED`.

## Licensing

By submitting a contribution, you agree that it may be distributed under the repository's license. You retain copyright in your contribution; no additional rights are granted beyond those needed to use, modify, and redistribute it under that license. Do not submit material whose license you cannot verify.

## Scope and safety

Alltron is intended to run on hardware controlled by its operator. Contributions must not silently enable remote access, expose a control endpoint to the internet, bypass Home Assistant permissions, or execute arbitrary model-generated commands. Home actions should be bounded, reviewable, and fail safely. Raise design concerns early when a change could affect household safety or privacy.
