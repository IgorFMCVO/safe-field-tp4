# SAFE-FIELD autonomous operational scenario report

Generated: 2026-09-05T16:11:36.880+00:00

All speech is fictitious offline SAPI TTS. No operator voice, person or real occurrence was used.
The committed transcript fixtures are semantic ground truth; they are not labelled as ASR output.
This is a fixture-orchestration regression, not acceptance of the complete acoustic chain: speaker clustering is calibrated with the fixture labels, hypothesis/fact expectations are supplied by the manifest, the wearable is an in-memory contract double, and the timing probe uses deliberate scheduler delays.

| Scenario | Fixture result | Speakers expected/detected | Re-ID | False merges | False splits | Roles | Facts P/R | DIAO |
|---|---|---:|---:|---:|---:|---:|---:|---|
| A_conflict_four_speakers | PASS | 4/4 | 1.000 | 0 | 0 | 1.000 | 1.000/1.000 | SUPPORTED |
| B_reidentification_order | PASS | 3/3 | 1.000 | 0 | 0 | 1.000 | 1.000/1.000 | SUPPORTED |
| C_ambiguous_threat | PASS | 3/3 | 1.000 | 0 | 0 | 1.000 | 1.000/1.000 | SUPPORTED |

- Hallucinated facts: 0.
- Average role accuracy: 1.000.
- Fixture-orchestration result: PASS.
- Full operational scenario acceptance: BLOCKED/FAIL while multi-speaker diarization remains 1/3 and the Pi→Razer/wearable deployment is not physically integrated.
- Capture/processing overlap: 3/3.
- Reassessment signalled when expected: 2/3.
- Acoustic speaker clustering is a transparent regression fixture, not civil biometric identification.
- Local pt-BR ASR is validated separately; physical-speech ASR and production diarization remain gated, and unavailable stages must return PROCESSING_PENDING.

## Synthetic scheduler-overlap probe (mean)

| Stage | Milliseconds |
|---|---:|
| segment→ASR | 0.099 |
| ASR→speakers | 0.016 |
| speakers→facts | 0.017 |
| facts→hypothesis | 0.023 |
| confirmation→DIAO | 2.357 |
| DIAO→watch | 10.806 |
| end-to-end | 13.317 |

These values measure only the deterministic scheduler-overlap fixture with configured sleeps; they are not model, network, wearable or end-to-end latency.
The complete local evidence package is under `mvp/evidence/autonomous_scenarios/` and is intentionally ignored by Git.
