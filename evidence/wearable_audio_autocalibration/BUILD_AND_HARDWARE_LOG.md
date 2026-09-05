# Build and hardware log — wearable audio autocalibration

Date: 2026-09-05

## Wearable

- Device: ESP32-S3 on `COM7` (`VID_303A:PID_1001`).
- Firmware: `wearable/safe_field_audio_autotest/`.
- Arduino core: Espressif `3.3.11`.
- Compile: PASS.
- Program storage: 1,484,635 bytes (47%).
- Dynamic RAM: 54,448 bytes (16%).
- Upload: PASS; flash segment hash verification PASS.
- Application image SHA-256:
  `22E0A75E07DAFFFCA41BDEC0314380A265F848A5A660EA5A48580A5B76637386`.
- Offline SAPI pt-BR WAV SHA-256:
  `48E598D6F612C615F50628B316A72EBD526678CB9E7D232AAE4A490B05F5AFCE`.
- Physical boot log confirmed ES8311 readiness, Wi-Fi IP `192.168.1.135`
  and HTTP self-test availability. No Wi-Fi password is present in this log.

## FPGA candidate

- Device detected by JTAG: `GW1NSR-4C`, ID `0x0100981B`.
- Programming mode: SRAM only; no flash operation.
- Bitstream SHA-256:
  `CA76E3B47FD0458E342E246A8A900E58A4DFF6F5DBB943AA2D1F041BB9D6C3F9`.
- Reference detector test: PASS, five checks.
- Synthesis: PASS.
- Place & Route: PASS.
- STA: PASS; setup slack `+1.482 ns`, hold slack `+0.708 ns`, TNS `0`.
- Resources: logic 1576/4608 (35%), registers 1009/3573 (29%),
  BSRAM 1/10 and DSP 0.5/8.

Warnings reviewed:

- `PA1001`: dangling generated carry/DSP nets; same Gowin tool-artifact class
  already present in the preserved baseline and not a timing violation.
- `PR1014`: generic clock routing for the validated fixed clock pin 45.
- `NL0002`: trivial `rasp_to_tang` net swept/inlined; the constrained package
  input and its LED/logic use remain present in the final pin/netlist reports.

The candidate was exercised in SRAM. After the independent Pi-to-Tang ACK
regression check, the frozen approved bidirectional bitstream was restored to
Tang SRAM. No TP4 file, FPGA flash or hardware connection was changed.

## Runtime restoration

- Raspberry serial link: `/dev/serial0 -> /dev/ttyS0`.
- GPIO14: `TXD1`; GPIO15: `RXD1`; GPIO17: output LOW.
- Existing SAFE-FIELD Core retained on port 8765.
- Normal `safe_field_hw_bridge.py` was restarted after exclusive UART testing.
- Restored bridge immediately received live CRC-valid QUIET telemetry.
- Watch HTTP and Core HTTP both returned `ok=true` after restoration.
