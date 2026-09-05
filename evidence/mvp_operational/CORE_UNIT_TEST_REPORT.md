# SAFE-FIELD operational core — unit-test evidence

- Date: 2026-09-05
- Scope: additive package `mvp/operational_intelligence` only
- Command: `python -m unittest discover -s mvp/tests -v`
- Result: **PASS — 77/77 tests**
- Elapsed reported by unittest: **15.168 s**

## Covered gates

| Behavior | Result |
|---|---:|
| START → ACTIVE → STOP → STANDBY | PASS |
| Required occurrence directory layout | PASS |
| Continuous `raw.wav`, including silence | PASS |
| Silence does not stop or gate capture | PASS |
| STOP flushes the last speech segment | PASS |
| Capture does not await a 250 ms ASR provider | PASS (capture call < 150 ms assertion) |
| Provider outage preserves WAV and pending job | PASS |
| ASR transcript is persisted before diarization and survives its failure | PASS |
| STOP timeout creates no incomplete history and retains active references | PASS |
| Retried STOP finalizes once without closing/duplicating capture | PASS |
| Fact without source is rejected | PASS |
| Hypothesis without supporting fact is rejected | PASS |
| Fact graph persisted with source-traceable nodes | PASS |
| Path-like artifact identifier is rejected | PASS |
| `S1 → S2 → S3 → S1` | PASS (3 detected, 0 false merge, 0 false split) |
| `S1 → S2 → S1 → S3 → S2` | PASS (3 detected, 0 false merge, 0 false split) |
| Ambiguous match is not silently merged | PASS |
| Officer confirmation precedes knowledge retrieval | PASS |
| Final Markdown/JSON contain traceable facts | PASS |
| PCM source opens transactionally on START | PASS |
| PCM source stops before `raw.wav` closes | PASS |
| Serial-open failure rolls back to STANDBY | PASS |
| Serial-stop failure preserves active recorder | PASS |
| PCM counters persist with the occurrence | PASS |
| PCM CRC/format/loss/read/sink failure blocks `FINISHED` and history | PASS |
| Repeated STOP after capture-integrity failure is idempotent | PASS |
| Watch API exposes terminal `CAPTURE_FAILED`, not generic processing wait | PASS |
| Pi→Razer redirects/proxies cannot forward bearer or audio | PASS |
| Pi→Razer idempotency capacity remains bounded with pending work | PASS |
| Remote ASR is persisted before downstream diarization failure | PASS |
| ASR latency p95 uses nearest-rank and includes cold-start outliers | PASS |

Speaker metrics above use deterministic embedding fixtures and validate registry
semantics, not the accuracy of a production diarization or embedding model.
Knowledge in this unit test is explicitly labelled `fixture-not-operational`; it
is not presented as real operational guidance.

The updated full-suite command is recorded in
`PIPELINE_DURABILITY_REGRESSION.md`.
