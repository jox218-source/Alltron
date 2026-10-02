# Speech engine and asset provenance

Evidence date: 2026-10-02. This is an inventory of the current public preview and open decisions, not a licensing approval or hardware result. No speech engine, model, voice, wake asset, recording, or other media is bundled in the repository or approved for distribution by this document.

| Component | Current public-tree evidence | Bundled / selected asset | Provenance and release requirement |
| --- | --- | --- | --- |
| Speech recognition | Optional adapter invokes a locally configured `whisper-cli`; configured through `ALLTRON_WHISPER_BIN` and `ALLTRON_WHISPER_MODEL`. The developer documentation points to the [whisper.cpp CLI documentation](https://github.com/ggml-org/whisper.cpp/tree/v1.9.4/examples/cli). | No executable or model is bundled. No model is selected for release. | Before distribution, record exact engine version/commit, source, checksum, applicable code license, exact model identifier/version, model card/source, checksum, license/terms, and review outcome. |
| Speech synthesis | Optional adapter invokes locally configured Piper CLI; configured through `ALLTRON_PIPER_PYTHON`, `ALLTRON_PIPER_MODEL`, and `ALLTRON_PIPER_CONFIG`. The developer documentation points to the [Piper CLI documentation](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/CLI.md). | No executable, voice model, or voice configuration is bundled. No voice is selected for release. | Before distribution, record exact engine version/commit and code license; for each voice, record exact model/version, model card or upstream record, checksum, voice/dataset provenance and terms, and review outcome. |
| Wake detection | The UI/API reports wake as disabled; no wake engine or runtime asset is selected in the current public-tree path. | No wake engine or asset is bundled or selected. | Select and assess an upstream implementation and exact asset only after provenance, license/terms, privacy behavior, and separate-Pi validation are reviewed. |

## Upstream code license checks (2026-10-02)

These are source observations for future dependency selection. No engine or
weights were installed into Alltron or added to its archive by this review.

| Upstream source inspected | Observed license evidence | Distribution status |
| --- | --- | --- |
| whisper.cpp `v1.9.4`, commit `927cfce34f31707e17f2bff35c349632fb9e2c3a` | The tagged [LICENSE](https://github.com/ggml-org/whisper.cpp/blob/927cfce34f31707e17f2bff35c349632fb9e2c3a/LICENSE) declares MIT. | Code license identified; binary build, transitive dependencies and exact converted model/checksum still require review. |
| OpenAI Whisper upstream model family | The official [Whisper README license section](https://github.com/openai/whisper#license) states that code and model weights use MIT. | No model selected or downloaded. A particular converted or quantized file still needs its source, conversion record, exact hash and accompanying notices. |
| Piper `v1.8.0`, commit `639388b6317fc4731e91d53da42aea68fd4166ff` | Tagged [package metadata](https://github.com/OHF-Voice/piper1-gpl/blob/639388b6317fc4731e91d53da42aea68fd4166ff/setup.py) declares GPL-3.0-or-later and ships [COPYING](https://github.com/OHF-Voice/piper1-gpl/blob/639388b6317fc4731e91d53da42aea68fd4166ff/COPYING). | Engine declaration identified; no binary or voice approved. Package dependencies and embedded assets need separate notices/source review. |

Piper's tagged [voice guide](https://github.com/OHF-Voice/piper1-gpl/blob/639388b6317fc4731e91d53da42aea68fd4166ff/docs/VOICES.md)
requires checking the individual voice model card for licensing. The engine's
license does not approve a voice or its training data. These inspected versions
are references, not promised supported appliance versions.

## Before distribution

Before bundling or recommending any engine, model, voice, wake asset, or media, the dependency/asset record must identify exact code version and license, exact model or voice identifier and version, model card or equivalent source record, checksums, voice/dataset provenance where applicable, all usage and redistribution terms, and a documented review. Review the engine code and each model/voice asset separately; a code license does not establish model or voice rights. Keep unapproved weights and media outside the repository and release archive.

Current interface and configuration evidence is in [VOICE_DEVELOPMENT.md](VOICE_DEVELOPMENT.md) and [src/alltron/voice.py](../src/alltron/voice.py). The upstream links above document the interfaces used by the existing developer path; they do not establish a selected release version, license conclusion, bundled asset, or supported hardware profile. No voice choice or hardware-performance claim is made here. Physical capture, playback, wake behavior, accuracy, latency, memory, thermal load, and supported-device claims require the separate hardware gate in [SOFTWARE_ACCEPTANCE.md](SOFTWARE_ACCEPTANCE.md).
