# SAFE-FIELD operational wearable v1 — build validation

Validation date: 2026-09-05

## Contract tests

Command:

```powershell
python .\tests\test_contract.py
```

Result: **PASS — 25/25 tests**.

Covered behavior:

- exact versioned GET/POST routes;
- occurrence lifecycle independent from FPGA VAD states;
- guidance hidden until `OFFICER_CONFIRMED`;
- three guidance action statuses;
- explicit reassessment state;
- official FT3168 touch integration;
- no camera flow, hardcoded IP or hardcoded Wi-Fi secret.
- bearer token loaded only from NVS and redacted from diagnostics;
- Authorization header on every GET and POST;
- fail-closed behavior without a token and explicit HTTP 401 handling.
- fail-closed rejection of plain HTTP, missing CA, URL credentials and paths;
- TLS certificate/hostname validation through `WiFiClientSecure::setCACert`,
  with redirects disabled and no insecure bypass;
- CA provisioning through redacted NVS state with bounded input;
- explicit `CAPTURE_FAILED` UI for non-retryable PCM integrity errors, honoring
  `capture_active/source_quiescent`: an active failed source remains stoppable,
  while a quiescent source cannot enter a finalization loop or history claim;
- preservation of explicit `capture_active=false` during finalization;
- normalization of `STOPPING` to the visible `PROCESSING_PENDING` state;
- valid handling of retryable 2xx `ok:false` finalization responses;
- distinct pending screens for capture-active processing and closed capture;
- production-disabled, explicitly opt-in `APPLY_JSON` test hook.

## Firmware compile

Command:

```powershell
.\BUILD.ps1
```

Result: **PASS** using Arduino-ESP32 3.3.11 and the local official Waveshare
libraries.

- Program storage: 1,126,335 / 3,145,728 bytes (35%).
- Dynamic memory: 50,240 / 327,680 bytes (15%).
- Application binary preserved as
  `build_artifacts/safe_field_operational_v1.ino.bin`.
- Binary size: 1,126,480 bytes.
- SHA-256: `0FEEC4A60FA9C9F4AB66A4ADE82BE22D35818589C931F1DA07C1B50829A41C6A`.

## Hardware mutation gate

No upload command was issued. The connected wearable firmware and all hardware
state were left untouched.
