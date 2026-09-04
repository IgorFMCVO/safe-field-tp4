# Physical validation — FPGA to Raspberry bridge

## Verdict

`FPGA_TO_RASPBERRY_PHYSICAL_BRIDGE = PASS`

This verdict is based on bytes received by the Raspberry from the programmed
Tang Nano 4K, not on simulation or visual LED observation.

## Layers verified

| Layer | Result | Evidence |
|---|---|---|
| JTAG identity | PASS — GW1NSR-4C, ID `0x0100981B` | `physical/jtag_scan_ft2ch.log` |
| SRAM programming | PASS — 100%, no Flash operation | `physical/sram_program.log` |
| Raspberry UART | PASS — `/dev/serial0 -> ttyS0`, RX GPIO15 ALT5 | `RASPBERRY_UART_CONFIGURATION.md` |
| protocol integrity | PASS — CRC accepted, seq/frame continuous | final JSONL below |
| physical FSM event | PASS — QUIET -> ACTIVE -> QUIET | final JSONL below |
| I2S health flag | PASS — no frame-error or overrun flag | flags `0x04` only |

## Final operator-synchronized capture

File:
`physical/raspberry_evidence/physical_voice_final_20260904T152402.jsonl`

- 3,264 valid protocol messages;
- sequence 62034 through 65297;
- zero sequence discontinuities;
- zero frame-counter step errors;
- exact increment of 256 audio frames per telemetry message;
- `frame_counter` wrapped correctly as an unsigned 32-bit field;
- energy range 775 to 25,829;
- states: QUIET for 902 records, ACTIVE for 414, QUIET for 1,948;
- flags `0x04` only: non-zero sample observed; no I2S frame error and no
  telemetry overrun.

The earlier retry capture is also retained. It had 6,560 records, zero sequence
or frame-step errors, energy peak 158,071 and at least one complete physical
QUIET -> ACTIVE -> QUIET transition.

## Interpretation

The FPGA emitted versioned UART telemetry derived from the frozen real-audio
pipeline; the Raspberry validated CRC and sequence, decoded the FPGA state and
persisted it as JSONL. This proves the requested first digital path. It does not
claim that PCM samples themselves are transported over UART.
