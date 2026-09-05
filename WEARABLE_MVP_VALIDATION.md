# SAFE-FIELD wearable MVP validation

Branch: `mvp-wearable-01`

## Target

`FPGA ACTIVE -> Raspberry -> HTTP -> wearable AUDIO_ACTIVE`

## Artifacts

- Firmware: `wearable/safe_field_one/safe_field_one.ino`
- Build helper: `wearable/safe_field_one/BUILD.ps1`
- Provisioning helper: `wearable/safe_field_one/PROVISION.ps1`
- Hardware audit: `docs/wearable/HARDWARE_AUDIT.md`

## Validation matrix

| Layer | Status | Evidence |
|---|---|---|
| USB / ESP32-S3 detection | PASS | COM7, VID_303A:PID_1001, esptool chip/flash identification |
| Original firmware recovery route | PASS | Official factory image and SHA-256 recorded |
| Firmware contract tests | PASS | 4/4 in `evidence/wearable/21_contract_tests.log` |
| Firmware compile | PASS | Arduino-ESP32 3.3.11; 1,101,955 bytes flash and 48,784 bytes RAM |
| Physical display boot | PASS | Operator confirmed `SAFE-FIELD / SISTEMA PRONTO / Audio QUIET` |
| Wi-Fi | PASS | `RZNET IGOR M - 2G`; password stored only in ESP32 NVS and redacted from logs |
| Core HTTP connection | PASS | Physical ESP32 repeatedly received HTTP 200 from `192.168.1.115:8765` |
| Tang / Raspberry bridge | PASS | GW1NSR-4C, validated SRAM image, continuous signed telemetry, flags `0x04` |
| QUIET -> ACTIVE -> QUIET | PASS | Real FPGA state reached Core and physical ESP32; transition and UI render logs below |
| End-to-end latency | PASS | API-to-render 0.409 s rising and 0.563 s falling; conservative FPGA-to-render bound below 0.75 s |

## Firmware and FPGA identity

- Wearable application SHA-256:
  `E1625E049531691E1806391364F07F13FA516B4412E7916A246D5695CFE65DEB`.
- Wearable upload verification: every flash segment hash verified by esptool.
- FPGA reloaded only in SRAM with the already validated bidirectional image.
- FPGA image SHA-256:
  `6E4C460162816C54EE38B11CDA246004C05FE07CEC4C1FA963FDBB36092E172F`.
- JTAG identity: `GW1NSR-4C`, ID `0x0100981B`.
- No FPGA RTL, TP4 file, pinout, UART wiring, or threshold was changed.

## Physical end-to-end event

The active Core occurrence recorded this sequence from real UART telemetry:

| Layer/event | Time (America/Sao_Paulo) | Seq | Energy |
|---|---|---:|---:|
| Raspberry/Core first QUIET | 22:41:12.062 | 3,856 | 1,994 |
| Raspberry/Core ACTIVE | 22:58:25.408 | 43,087 | 38,264 |
| Wearable API observer ACTIVE | 22:58:25.174 | 43,087 | 38,264 |
| Physical wearable vibration edge | 22:58:25.535 | - | - |
| Physical wearable rendered ACTIVE | 22:58:25.583 | - | - |
| Raspberry/Core returned QUIET | 22:58:30.067 | 43,843 | 2,783 |
| Physical wearable rendered QUIET | 22:58:30.480 | - | - |

The Raspberry and Razer clocks were not synchronized tightly enough to subtract
their absolute timestamps. The two observations made on the Razer clock give
0.409 s from API ACTIVE observation to wearable render and 0.563 s for the
return to QUIET. The implementation bound from an already asserted FPGA state
is approximately 0.75 s: UART packet time plus the Core follower's 30 ms loop
and the wearable's 700 ms polling interval.

The UI serial `STATE` message is emitted after `renderUi()` returns, so this is
an observation made inside the physical wearable, not an API-only inference.

## Repeatability note

Later operator attempts with ordinary voice, three separated claps, and one
sustained vowel remained in QUIET. Those attempts are retained rather than
hidden. The corresponding FPGA stream remained healthy: 25,184 inspected
records, all `flags=0x04`, zero sequence loss, energy from 753 to 27,244. The
short peaks did not satisfy the frozen FSM's 24-consecutive-window attack.
This does not change the PASS of the observed end-to-end transition, but it is
the first calibration/repeatability item for a later sprint. Per scope, no TP4
threshold or audio RTL was changed here.

## Evidence index

- `01_device_identification.log`: ESP32-S3/PSRAM/USB identity.
- `02_build_upload.log`: compile and verified wearable upload.
- `03_wifi_core_provision.log`: redacted Wi-Fi provisioning and HTTP 200.
- `06_tang_jtag_rescan.log`: physical GW1NSR-4C identity.
- `07_validated_fpga_sram_program.log`: exact frozen image programmed to SRAM.
- `08_quiet_serial.log`: physical wearable received `AUDIO_QUIET`.
- `11_physical_transition_retry_serial.log`: wearable render/vibration and
  ACTIVE-to-QUIET transition.
- `12_physical_transition_retry_api.log`: API state transition with FPGA
  sequence and energy.
- `13` through `20`: retained non-triggering repeat attempts.
- `21_contract_tests.log`: self-checking contract tests.

## Current conclusion

`SAFE_FIELD_WEARABLE_MVP = PASS`

The physical ESP32 booted the SAFE-FIELD interface, joined Wi-Fi without a
versioned secret, polled the existing Raspberry Core, received a real FPGA
ACTIVE event, rendered `AUDIO_ACTIVE`, vibrated once on the rising edge, and
rendered QUIET again. Reproducible triggering by ordinary speech is explicitly
deferred as calibration work and did not cause a forbidden TP4 modification.
