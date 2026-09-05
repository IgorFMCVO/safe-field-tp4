# SAFE-FIELD — audio autocalibration report

Date: 2026-09-05

## Final result

`VOICE_DETECTION_AUTONOMOUS = FAIL`

The process was stopped at the physical-playback gate, before calibration. The
watch accepted every HTTP self-test command, initialized the official ES8311
driver and submitted every expected PCM byte to its I2S peripheral. However,
speech playback at volumes 40, 65 and 85 did not produce a reproducible energy
increase in the independently live INMP441/FPGA telemetry. Fitting thresholds
to these windows would fit ambient drift rather than the known stimulus.

## Layer isolation

| Layer | Result | Evidence |
|---|---|---|
| ESP32-S3 boot, Wi-Fi and HTTP | PASS | physical serial boot and self-test status |
| ES8311 I2C initialization | PASS | `audio_ready=true` |
| PCM submitted to ESP_I2S | PASS | 539184/539184 bytes for each speech run |
| Speaker-to-air-to-INMP441 coupling | FAIL / not observable | no reproducible playback-energy increase |
| INMP441-to-FPGA-to-Pi telemetry | PASS | live non-zero frames, CRC and sequence valid |
| Runtime Pi-to-FPGA commands | FAIL (separate regression) | no ACK with new or frozen approved bidirectional bitstream |
| Candidate detector model | PASS in self-checking reference test | old misses discontinuous speech; K-of-N detects it |
| Candidate detector physical acceptance | FAIL / blocked | playback prerequisite failed |

The exact physical boundary remaining for playback is after the successful
digital I2S write: speaker transducer/connector, NS4150-to-SPK path, or acoustic
coupling. Independently, Raspberry physical pin 8 to Tang package pin 46 failed
its regression while GPIO14 remained muxed as TXD1. Neither result is attributed
to the candidate detector RTL, and no wire was touched.

## Autonomous measurements

| Watch volume | Pre-silence RMS | Playback RMS | Post-silence RMS | Playback/max(silence) | Result |
|---:|---:|---:|---:|---:|---|
| 40 | 8427.058 | 8056.573 | 6654.621 | 0.9560 | FAIL |
| 65 | 8588.252 | 6383.986 | 5066.260 | 0.7433 | FAIL |
| 85 | 7941.446 | 7857.468 | 5220.796 | 0.9894 | FAIL |

- Noise-floor p95 across autonomous silence windows: `15712.6` energy units.
- CRC errors: `0`.
- Sequence losses: `0`.
- FPGA frame errors: `0`.
- Telemetry overruns: `0`.
- Operator speech, claps or readiness prompts: `0`.
- Calibration cycles accepted: `0/10`; the ten-cycle test was intentionally
  not run after all three physical playback gates failed.

## Detector revision

The frozen detector requires 24 consecutive energy windows above the ON
threshold, so ordinary speech gaps reset its attack counter. The branch-only
candidate uses a runtime-configurable 8-of-24 vote, one qualifying attack
window, 16 release windows and 82 hangover windows. Runtime parameters live in
registers only. The candidate remains a model/build result, not a physically
accepted calibration.

Historical physical data still proves that the INMP441 responds to real voice:
voice RMS was 4.9926 times the independent silence capture. It also records 100
old-FSM transitions in a 99.42-second run. Because the later operator markers
were explicitly marked unsynchronized/inconclusive, this evidence is not
silently relabelled as a 10/10 detector acceptance. The machine-readable audit
is `evidence/wearable_audio_autocalibration/existing_physical_dataset_audit.json`.

## Build evidence

- FPGA bitstream: `mvp_audio_autocalibration/build_artifacts/safe_field_mvp_audio_autocalibration.fs`
- FPGA SHA-256: `CA76E3B47FD0458E342E246A8A900E58A4DFF6F5DBB943AA2D1F041BB9D6C3F9`
- P&R: PASS.
- STA: PASS; setup slack `+1.482 ns`, hold slack `+0.708 ns`, TNS `0`.
- Wearable firmware compile: PASS; 1,484,635 bytes flash, 54,448 bytes dynamic RAM.
- Physical programming: ESP32 flash hash verified; Tang test bitstream used SRAM
  only. The frozen approved bidirectional bitstream was restored to Tang SRAM
  after the regression cross-check.

Raw CSV, console log and machine-readable result are preserved under
`evidence/wearable_audio_autocalibration/`.
