# Privacy and data handling

## Current status

Alltron is pre-alpha and its final data flows are not yet implemented or verified. This document describes project requirements and intended behavior, not a claim that every control is already available. Confirm actual behavior in the current release before connecting household services.

## Intended design

- Audio capture and speech recognition should run on the Alltron device using the configured local speech components.
- Home Assistant and Codex credentials should be supplied by the operator during local setup and remain on that device. Alltron should not ask contributors to send credentials to maintainers.
- Voice requests sent to an LLM provider through the operator's authenticated CLI may leave the home network. The provider's account, CLI, retention, and service terms govern that processing. The UI and setup guide must explain this before enabling the feature.
- Personal-file answers are outside the initial public project scope.
- Logs should be local, bounded, and redacted by default. Audio and transcripts should not be retained unless the operator explicitly enables a documented feature.

## Operator checklist

Before connecting real services, review what audio, transcript, prompt, entity metadata, and action details leave the device; where credentials are stored; how logs are retained; and how to remove configuration and history. Use a dedicated test Home Assistant instance until behavior is validated.

## Contribution and issue data

Do not commit secrets, household details, recordings, real entity IDs, or personal configuration. Use fictional examples. Redact logs before submitting them in a public issue. GitHub processes issue and contribution data under its own terms and privacy policy.

## Changes to this document

As implementation lands, replace intended-behavior statements with verified facts, describe each data flow and retention control, and link to the exact configuration or code. Do not claim local-only processing while an enabled provider or authentication flow sends data elsewhere.
