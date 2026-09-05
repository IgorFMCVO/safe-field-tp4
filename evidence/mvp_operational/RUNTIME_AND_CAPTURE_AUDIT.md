# Runtime and physical capture evidence

Audit time: 2026-09-05 10:49:11 -03; final local update: 2026-09-05.

```text
host: safe-field
arecord -l: no capture devices listed
core at initial snapshot: safe_field_core.py on TCP 8765
bridge at initial snapshot: safe_field_hw_bridge.py on /dev/serial0 at 115200 baud
```

```text
Razer GPU: NVIDIA GeForce RTX 4090 Laptop GPU, 16376 MiB
driver: 551.95
driver CUDA capability: 12.4
Faster-Whisper: 1.2.1 (isolated ignored venv)
CTranslate2: 4.8.2
validated inference: CPU/int8
GPU inference: BLOCKED, cublas64_12.dll unavailable
pt-BR TTS subset: 6 files, mean WER 0.0922, PASS
all fixtures: 16/16 non-empty, cross-locale mean WER 0.4241, stress FAIL retained
SpeechBrain ECAPA: CPU, 192D, 3/3 re-ID scenarios PASS
ECAPA model SHA-256: 0575CB64845E6B9A10DB9BCB74D5AC32B326B8DC90352671D345E2EE3D0126A2
```

Source inspection confirms frozen UART protocol v1 contains telemetry only.
The initial bridge snapshot above is historical: it was stopped before the PCM
gate so it could not contend for the serial port. The separate MVP PCM protocol
was built and physically tested in SRAM at 1.5 Mbaud. The final hardened
60.010637 s run received 79,084 valid frames / 2,530,688 samples, with CRC,
format, sequence/sample losses, startup/resync, discontinuities, I2S frame
errors and overruns all zero.
The captured window contained no controlled speech, so it does not claim
physical ASR. Speaker embedding/re-ID is now validated locally with ECAPA, but
multi-speaker diarization remains blocked: the autonomous CRDNN-VAD + ECAPA
experiment passed only 1/3 multi-speaker scenarios and was not connected to the
runtime. No fixture value was substituted as real ASR output, and no occurrence
data was uploaded.

The validated receiver is now wired additively into the WATCH lifecycle behind
`--pcm-port`: serial open is part of START, the source is stopped before the WAV
recorder on STOP, and protocol counters are exposed live and persisted. The
integration passed 77/77 Core/API tests and 13/13 receiver/protocol tests. A
Python utility exercising the same START→UART→`raw.wav`→STOP contract captured
421,760 physical samples, generated an empty lifecycle-only history and retained
zero error counters; it was not a physical wearable-touch test. The final hardened rerun
`PHYSICAL_WATCH_PCM_003` also verified zero post-lock resync, zero sequence or
sample discontinuity, exact packet/sample/WAV invariants and 0.999727 of the
expected sample rate. A second 60.010637 s run captured 2,530,688 samples with
all new gates at zero and a 0.999778 rate ratio. A controlled-speech WATCH
session remains the physical capture-to-ASR gate; multi-speaker diarization
also remains blocked pending a local pipeline/model. The hardened Pi→Razer
protocol is implemented and passed loopback/fake-provider tests, but no LAN/TLS
deployment or physical wearable integration is claimed.
