# SAFE-FIELD MVP — consolidated acceptance report

Date: 2026-09-05 (America/Sao_Paulo)
Branch: `mvp-operational-intelligence-v1`

## Decision

`MVP_STATUS = PARTIAL`

The physical PCM collector, continuous occurrence lifecycle, local ASR,
speaker embedding/re-identification, traceable reasoning contracts, real local
DIAO retrieval, preliminary-history generation and operational wearable build
are implemented. The complete MVP is not accepted because multi-speaker
diarization passed only 1/3 controlled scenarios. The Pi→Razer transport and
operational wearable have passed contract/build tests but have not been
deployed together over the physical LAN/watch path.

## Evidence classification

| Gate | Result | Evidence class | Measured evidence / limitation |
|---|---|---|---|
| Capture | PASS | physical | FPGA→Pi UART PCM, 2,530,688 samples in 60.010637 s; all corruption/loss/discontinuity counters zero |
| Occurrence START/STOP capture lifecycle | PASS | physical UART + software utility | 421,760 samples; ordered close; zero segments/jobs because the window contained no controlled speech; not a wearable-touch test |
| Segmentation | PASS | replay/unit | pre/post-roll, silence close and STOP flush; silence never gates global recording |
| ASR | PASS | real local model on offline TTS | Faster-Whisper small CPU/int8; 16/16 non-empty; native pt-BR mean WER 0.0922; cross-locale stress WER 0.4241 remains FAIL |
| Physical-speech ASR | UNCLAIMED | no controlled-speech window | physical PCM transport does not by itself prove acoustic ASR |
| Multi-speaker diarization | FAIL/BLOCKED | real local model experiment | CRDNN VAD + ECAPA + clustering: 1/3 scenarios PASS; A 4/6, B 3/4, C 3/3 |
| Speaker embedding / re-ID | PASS | real local neural model, controlled turns | ECAPA 192D; A 4/4, B 3/3, C 3/3; accuracy 1.000; zero false merges/splits |
| Role classification | PASS | deterministic transcript fixtures | 1.000 accuracy; content/context only; no timbre-based role inference |
| Fact extraction | PASS | deterministic transcript fixtures | precision 1.000, recall 1.000, hallucinated facts 0; exact source spans enforced |
| Hypothesis/reassessment | PASS | controlled reasoning tests | provisional, source-backed and officer-confirmation state machine; no guilt/lying conclusion |
| Watch confirmation contract | PASS | HTTP/firmware simulation | versioned routes and production-disabled test hook; firmware compile PASS; physical operational firmware not flashed |
| DIAO document/index | PASS | real local source | 2,161 pages, 2,161 native-text pages, 19,129 chunks, source SHA verified, PDF/index ignored by Git |
| DIAO retrieval/guidance | PASS | real local source + controlled hypotheses | 15/15 query variants rank 1, stable 15/15, 3/3 sourced scenarios, unsupported guidance 0 |
| Final history | PASS | controlled semantic scenarios | Markdown/JSON generated from persisted traceable artifacts; physical lifecycle history was structurally valid but semantically empty |
| Pi→Razer worker protocol | PASS | loopback/fake-provider contract | auth, hashes, idempotency, limits, redirect/proxy blocking, safe pending/retry and spool TTL; LAN/TLS deployment pending |
| Complete A/B/C autonomous chain | FAIL/BLOCKED | mixed | fixture orchestration is 3/3, but it uses labelled calibration/expected semantics and cannot override the diarization failure |

The physical numeric claims above are independently readable in the tracked
JSON files under `evidence/mvp_operational/physical_pcm_transport/`; WAVs remain
private and ignored. `PHYSICAL_MACHINE_EVIDENCE_MANIFEST.md` records the hashes
of the corresponding original private JSON artifacts and packages.

## Final regression matrix

| Command | Result |
|---|---:|
| `python -m unittest discover -s mvp/tests -p "test_*.py" -v` | PASS — 77/77 in 15.168 s |
| `python -m unittest discover -s operational_guidance/diao/tests -p "test_*.py" -v` | PASS — 10/10 |
| `python -m unittest discover -s raspberry/safe_field_core/tests -p "test_*.py" -v` | PASS — 6/6 |
| `python -m unittest discover -s raspberry/tests -p "test_*.py" -v` | PASS — 5/5 |
| `python -m unittest discover -s raspberry_mvp/pcm_stream/tests -p "test_*.py" -v` | PASS — 13/13 |
| `python -m unittest discover -s wearable/safe_field_operational_v1/tests -p "test_*.py" -v` | PASS — 25/25 |
| `python -m mvp.operational_intelligence.local_ai_selftest` | PASS — 5/5 |
| `python operational_guidance/diao/audit_index.py` | PASS — all integrity checks |
| `python operational_guidance/diao/tests/evaluate_retrieval.py` | PASS — 15/15, 3/3 sourced, 0 unsupported |
| `node verilog_mvp/pcm_stream/sim/run_pcm_stream.mjs` | PASS — packet and sustained-rate simulations |
| `python -m compileall ...` | PASS |

## Model and retrieval latency

These stages were measured independently; no complete physical end-to-end
latency is reported while diarization/deployment remain blocked.

| Measurement | Result |
|---|---:|
| ASR mean, cold-inclusive | 1,547.8 ms/file |
| ASR p95, cold-inclusive, nearest-rank | 2,227.3 ms/file |
| ASR warm mean / p95 | 1,502.5 / 1,780.0 ms/file |
| ECAPA cold / warm mean / warm p95 | 2,472.599 / 230.259 / 358.547 ms |
| DIAO provider load | 1,866.393 ms |
| DIAO warm query median / p95 / max | 225.065 / 272.331 / 306.273 ms |

The timings in `AUTONOMOUS_TEST_REPORT.md` are deliberately labelled as a
synthetic scheduler-overlap probe; they come from configured sleeps and are not
model, network, watch or end-to-end latency.

## Safety and privacy

- The TP4 RTL/build/deliverables were not modified.
- Camera, face recognition and civil biometrics remain outside scope.
- The real DIAO PDF, extracted text, index, generated audio, local model bundles
  and session artifacts remain ignored and untracked.
- No occurrence/audio/DIAO content was sent to an external service.
- No password, bearer token, Wi-Fi credential or model secret is stored in the
  repository.
- Unsupported or unavailable stages fail closed as `PROCESSING_PENDING`,
  `GUIDANCE_NOT_AVAILABLE` or `GUIDANCE_NOT_SUPPORTED`; no procedure is invented.

## Remaining blocker

A validated local speaker-change/overlap diarization pipeline is required.
After it passes the controlled scenarios, deploy the authenticated Pi→Razer
transport and the compiled operational watch firmware, then perform one single
physical START→speech→confirm→DIAO→STOP acceptance session.
