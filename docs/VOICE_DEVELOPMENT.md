# Local speech development path

Evidence date: 2026-09-24. This is an opt-in developer path, not an appliance installer or a supported Raspberry Pi profile. The default preview leaves microphone capture, wake detection, transcription and speech output disabled.

## Current behavior

The browser sends start, stop and cancel controls to the loopback API. If configured, one service-owned ALSA `arecord` process captures 16 kHz mono PCM for push-to-talk. It continues across browser refreshes. Alltron bounds a recording to 30 seconds, rejects silent audio, writes a private temporary WAV for `whisper-cli`, routes recognized text through the explicit local command grammar, and can send the short response to Piper and `aplay`. Temporary WAV files are removed after the request. The in-memory event list expires after two minutes and is not written to the database; command effects such as a timer or shopping item are durable.

Wake detection remains disabled. No wake model, Whisper model, Piper voice or engine binary is bundled. The current Piper adapter starts a new CLI process per reply, so first audio latency may be poor. A resident candidate still needs implementation and a measured comparison. Engine `ready` means required paths and executables were found; `verified` stays false until a successful speech operation in this session. A configured microphone process likewise does not prove usable acoustics. Live setup and separate-Pi acceptance are deferred to Stage 4.

## Contributor configuration

Use disposable hardware or a development machine with the listed engines installed from their upstream projects. Keep models and voice assets outside the Git tree. Select an ALSA input and output by device name; the installer will eventually guide and verify this choice. Set these environment variables for the service process:

| Variable | Purpose |
| --- | --- |
| `ALLTRON_AUDIO_INPUT` | Selected ALSA capture device; enables the persistent recorder. |
| `ALLTRON_AUDIO_OUTPUT` | Selected ALSA playback device; enables service alarm audio and Piper playback when dependencies are present. |
| `ALLTRON_WHISPER_BIN` | Local `whisper-cli` executable. |
| `ALLTRON_WHISPER_MODEL` | Local compatible Whisper model file. |
| `ALLTRON_WHISPER_THREADS` | Positive CPU thread count; default is `2`. |
| `ALLTRON_PIPER_PYTHON` | Python executable in an isolated environment with `piper-tts`. |
| `ALLTRON_PIPER_MODEL` and `ALLTRON_PIPER_CONFIG` | Matching local Piper ONNX model and configuration files. |
| `ALLTRON_VOICE_SCRATCH` | Optional private directory for temporary inference files. |

The adapter uses the upstream [whisper.cpp CLI](https://github.com/ggml-org/whisper.cpp/tree/v1.9.4/examples/cli) and [Piper CLI](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/CLI.md) interfaces. These links document interface intent, not an approved distribution bundle. Before any installer downloads or release archive includes engines or models, record exact versions, checksums, licenses, voice/model terms and ARM64 compatibility in a reviewed dependency manifest. Do not package a private voice, wake model, recording or configuration as a shortcut.

## Acceptance deferred until dedicated hardware

The next project work is Stage 2 HA/Codex owner integration and Stage 3 software installation/recovery. The following speech checks wait for a separate Alltron test Pi in Stage 4; the existing private Pi is not an Alltron test device.

- With a fictional spoken sample, verify direct recognition, full mic-to-command-to-reply flow, silence handling, cancellation, and that playback does not retrigger wake.
- Verify the selected microphone and speaker after reboot and browser refresh. A healthy worker or synthetic tone is insufficient.
- Test alarm playback and missed-alarm reporting with the service running and after power loss.
- Measure recognition accuracy, first audio latency, memory, CPU and thermals while Home Assistant, Codex and kiosk run together on a separate, allowlisted Pi.
