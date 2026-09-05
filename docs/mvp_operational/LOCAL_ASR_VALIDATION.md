# Local ASR validation

Generated: 2026-09-05T16:06:01.309+00:00

This run used the actual Faster-Whisper model against offline SAPI WAV files.
Fixture transcripts were used only as ground truth and were never substituted as output.
No audio or occurrence data was uploaded.

- Result: **PASS**
- Model path class: local ignored directory (`faster-whisper-small`)
- Device / compute type: `cpu` / `int8`
- Files transcribed: 16/16
- Empty outputs: 0
- pt-BR-voice files: 6
- pt-BR-voice mean WER: 0.0922
- All-voice stress mean WER: 0.4241
- All-voice stress median/worst WER: 0.5417/0.8462
- Mean inference time, cold-inclusive: 1547.8 ms/file
- p95 inference time, cold-inclusive (nearest-rank): 2227.3 ms/file
- First/cold inference: 2227.3 ms
- Mean/p95 after cold start: 1502.5/1780.0 ms/file

Acceptance for the pt-BR ASR gate: every WAV yields non-empty output and the native pt-BR SAPI voice has mean WER ≤ 0.25.
The all-voice stress set is **FAIL** at its original mean-WER ≤ 0.35 target; the failures are retained because the only additional installed voices are en-US voices forced to speak Portuguese.
This closes the autonomous/model ASR gate. Physical INMP441→PCM delivery and WATCH-controlled raw capture are separately PASS; ASR over a controlled physical-speech window remains unclaimed.

| Scenario/segment | WER | confidence | latency ms |
|---|---:|---:|---:|
| A_conflict_four_speakers/segment_001 | 0.000 | 0.820 | 2227.3 |
| A_conflict_four_speakers/segment_002 | 0.625 | 0.488 | 1597.9 |
| A_conflict_four_speakers/segment_003 | 0.667 | 0.585 | 1728.8 |
| A_conflict_four_speakers/segment_004 | 0.000 | 0.838 | 1363.1 |
| A_conflict_four_speakers/segment_005 | 0.143 | 0.753 | 1317.5 |
| A_conflict_four_speakers/segment_006 | 0.250 | 0.529 | 1503.6 |
| A_conflict_four_speakers/segment_007 | 0.733 | 0.443 | 1576.9 |
| B_reidentification_order/segment_001 | 0.333 | 0.785 | 1330.2 |
| B_reidentification_order/segment_002 | 0.692 | 0.392 | 1368.5 |
| B_reidentification_order/segment_003 | 0.000 | 0.807 | 1395.1 |
| B_reidentification_order/segment_004 | 0.583 | 0.535 | 1635.8 |
| B_reidentification_order/segment_005 | 0.700 | 0.464 | 1296.5 |
| C_ambiguous_threat/segment_001 | 0.077 | 0.790 | 1415.7 |
| C_ambiguous_threat/segment_002 | 0.846 | 0.430 | 1503.3 |
| C_ambiguous_threat/segment_003 | 0.500 | 0.470 | 1780.0 |
| C_ambiguous_threat/segment_004 | 0.636 | 0.446 | 1724.6 |
