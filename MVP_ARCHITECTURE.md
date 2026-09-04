# SAFE-FIELD MVP architecture

## Implemented path

```text
physical sound
    -> INMP441 ADC / I2S
    -> Tang Nano 4K deterministic energy + FSM
    -> UART protocol v1, 115200 8N1
    -> Raspberry parser + CRC/sequence validation
    -> JSONL + occurrence timeline + local HTTP API
```

The FPGA publishes state, energy, audio-frame counter and error flags. It does
not stream PCM in this MVP.

## Session layout

```text
sessions/<session-id>/
  session.json
  events.jsonl
  photos/
  audio/
  reports/
```

## Boundaries

- audio acquisition/calibration is the frozen TP4 baseline;
- UART bridge is a separate bitstream and does not overwrite the baseline;
- camera backend is UVC-only in production and truthfully reports absence;
- mock camera is opt-in development behavior;
- no face recognition, biometrics, transcription or fact extraction is in this
  stage;
- the future wearable consumes the local state contract; it does not replace
  FPGA control.
