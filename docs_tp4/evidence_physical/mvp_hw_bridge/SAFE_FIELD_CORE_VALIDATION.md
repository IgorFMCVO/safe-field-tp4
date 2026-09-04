# SAFE-FIELD core and camera scaffold validation

## Automated tests

`raspberry/safe_field_core/tests/test_safe_field_core.py`: **6/6 PASS** on the
development computer and **6/6 PASS** on the Raspberry.

Coverage includes:

- session layout and lifecycle;
- FPGA event persistence and timeline;
- wearable state mapping;
- explicit camera mock labeling;
- absent-camera behavior without fake image;
- rejection of Linux video nodes whose driver is not `uvcvideo`.

## Physical Raspberry execution

Session: `20260904T182058Z_f31005b8`.

- 624 real FPGA telemetry events ingested;
- occurrence status endpoint returned current FPGA state/energy/counters;
- timeline recorded `OCCURRENCE_STARTED`, FPGA events, `AUDIO_QUIET` and
  `OCCURRENCE_FINISHED`;
- photo capture returned HTTP 409 and exact status `CAMERA_NOT_CONNECTED`;
- no JPEG was fabricated;
- occurrence finish persisted `ended_at`.

Raw evidence is under:
`physical/raspberry_evidence/core_physical_bundle_20260904T152056/`.

## Scope

The camera is intentionally disconnected. UVC support is implemented but could
not be physically accepted without a camera. No face recognition, biometric
classification, institutional lookup or AI analysis is implemented.
