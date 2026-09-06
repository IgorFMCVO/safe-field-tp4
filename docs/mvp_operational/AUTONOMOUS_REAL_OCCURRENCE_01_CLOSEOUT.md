# Autonomous occurrence 01 — PARTIAL

Date: 2026-09-06. Branch: `mvp-autonomous-real-occurrence-01`.
Base: `fb92e1367d7c9d2e72a193ad395557d2171f620c`.
Session: `sessions/OCC-SIM-20260906T135545Z/` (private, ignored).
Absolute root: `C:\SAFE-FIELD\fpga\tp4-audio-inmp441\sessions\OCC-SIM-20260906T135545Z`.

## Scope and result

This is an entirely fictional, local software simulation, not a physical validation,
actual police occurrence or operationally approved report. TP4, FPGA, UART, camera,
Raspberry and wearable hardware were not modified. No operator participation or
external consultation was used. No push was performed.

The real local DIAO index was queried before authoring the scenario. Selected
provisional nature: B01.147, AMEACA; operational source page 103, items a–e.
PDF SHA-256: `747B1EE9E50FC799053CD34F00DCE848DF8EB75AB99B73FE9E92967B1CC91ADA`.
This identifies the supplied source, not its current legal validity. Source text,
retrievals, audio and generated occurrence records remain outside Git.

Five distinct Windows OneCore voices generated 24 Portuguese utterances:
Daniel and Maria (pt-BR), Mark, David and Zira (en-US). No pitch shifting was used.
The English voices speaking Portuguese are a material realism/ASR limitation,
not evidence that the physical microphone or human Portuguese recognition failed.
WAV: 717.632 s, mono PCM16 at 16 kHz, including 90 s continuous silence.

Faster-Whisper small CPU/int8, SpeechBrain CRDNN VAD and ECAPA received anonymous
audio only. Their real outputs were cached by PCM hash and replayed through the
existing Core and authenticated loopback HTTP API at 30x. The existing local
rule-based reasoner received actual transcripts and predicted identities, not
the authored script or participant labels. Ground truth was joined only during
post-inference evaluation. Replay/cache timing is not heavy-worker throughput.

| Layer | Result | Measurement |
|---|---|---|
| Continuous capture | PASS | Source PCM preserved; 90 silence checks remained ACTIVE |
| Segmentation | PASS | 24 nonempty segments |
| ASR | FAIL | WER 41.12%; 336 substitutions, 24 deletions, 87 insertions / 1087 reference words |
| Online speaker registry | FAIL | 8 identities for 5 people; 7 dominant identities |
| Online re-ID | FAIL | 11/19 returns correct (57.89%); 0 false-merge pairs, 8 false-split pairs |
| Isolated embedding re-ID | PASS | 5 identities, 19/19 returns, 0 merges/splits; NOT substituted into runtime |
| Roles | FAIL | 0/5 final roles correct, including 0/2 officers |
| Fact extraction | PARTIAL | Lexical precision proxy 74.4%; anchor recall 14/29 (48.28%) |
| Hallucination gate | NOT PROVEN | 0 additions beyond ASR text, but 32 sentences lack sufficient reference support |
| Hypothesis / DIAO | PASS, simulation scope | Confirmation precedes one real retrieval; 5 sourced priorities, 0 unsupported guidance |
| Wearable API | PASS, software only | START, hypothesis, confirmation, 3 action statuses, STOP |
| History / draft files | PASS generation, PARTIAL content | Preserved noisy transcripts and warnings; not an approved police report |
| FIELD_NOISE | NOT RUN | CLEAN acceptance failed |

Exactly three whole-recording diarization configurations were evaluated:

| Trial | CRDNN merge gap | Embedding window | Clustering | Clusters | DER |
|---|---:|---:|---|---:|---:|
| 1 | 0.2 s | 30 s | Agglomerative, distance 0.25 | 15 | 11.33% |
| 2 (preselected for replay) | 0.6 s | 30 s | Agglomerative, distance 0.25 | 9 | 8.21% |
| 3 | 0.6 s | 3 s | Spectral | 32 (cap) | 19.04% |

Trial 2 matched all 23 expected speaker changes within 0.75 s but predicted 28
changes (82.14% precision). Dominant-turn matching hides small extra clusters;
therefore DER alone does not approve diarization. No fourth iteration was run.

## Integration corrections and verification

- Pool multiple embedding windows from the same local diarization identity into
  one duration-weighted normalized centroid before online registry assignment.
  This reduced registry fragmentation from 17 to 8, but did not pass the gate.
- Choose the latest hypothesis by creation time, not lexical hash filename.
- Persist simulated wearable commands to timeline/history and preserve action
  statuses across polling, bound to the corresponding hypothesis.
- Five new regression tests cover these paths and WER accounting.
- Existing oversized-body rejection test now sends headers without a body. This
  directly verifies HTTP 413 before body reading and avoids a Windows TCP-close
  race (WinError 10053). Earlier failing logs are preserved, not deleted.

Final MVP regression suite: **82/82 PASS**.
Log: `mvp/evidence/real_occurrence_01/regression_tests_verified.log`.
Manifest verification: **300/300 files exist and match SHA-256**.
Ground truth and generated WAV were explicitly checked as Git-ignored.

## Reproduction commands

Run from the project root above. These are the executed script entry points;
do not rerun generation into the preserved evidence directory merely to view it.
Python below means `mvp/evidence/local_ai_venv/Scripts/python.exe`.

```powershell
python -m mvp.tests.real_occurrence_scenario
powershell.exe -NoProfile -File mvp/tests/occurrence_voice_synthesis.ps1 -Manifest mvp/evidence/real_occurrence_01/scenario_ground_truth.json
python -m mvp.tests.real_occurrence_audio
python -m mvp.tests.real_occurrence_inference --audio mvp/evidence/real_occurrence_01/full_occurrence_mix.wav --output mvp/evidence/real_occurrence_01/inference
python -m mvp.tests.real_occurrence_inference --audio mvp/evidence/real_occurrence_01/full_occurrence_mix.wav --output mvp/evidence/real_occurrence_01/inference --reid-only
python -m mvp.tests.real_occurrence_replay --audio mvp/evidence/real_occurrence_01/full_occurrence_mix.wav --cache mvp/evidence/real_occurrence_01/inference/cache --speed 30
python -m mvp.tests.real_occurrence_report --session sessions/OCC-SIM-20260906T135545Z
python -m unittest discover -s mvp/tests -p 'test_*.py' -v
```

## Private deliverables

Inside the session's `reports/` directory:

- `ABRIR_SIMULACAO.html`: complete readable report plus actual generated audio.
- `AUTONOMOUS_REAL_OCCURRENCE_SIMULATION_REPORT.md`: complete interaction timeline,
  transcripts versus reference, roles, metrics, retrieval, limitations and draft.
- `WATCH_COMMAND_SEQUENCE.md`, `SPEAKER_ASSIGNMENT_REPORT.md`,
  `ROLE_CLASSIFICATION_REPORT.md`, `FACT_EXTRACTION_REPORT.md`.
- `HISTORICO_PRELIMINAR.md` and `.json`.
- `BO_RELATO_POLICIAL_PRONTO.md` and `.txt`: explicitly preliminary, requires review.
- `SIMULATION_METRICS.json`, `STORAGE_MANIFEST.json` and `.md` with absolute paths.

No Raspberry mirror exists. Earlier replay sessions remain preserved.
Next step: improve Portuguese voice suitability and integrated diarization/role
acceptance in a separate experiment; do not promote this draft to operational use.
