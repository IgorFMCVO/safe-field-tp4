# SAFE-FIELD RAW_I2S_24_CAPTURE

Additive diagnostic build for observing the exact signed 24-bit word produced
by the frozen I2S receiver beside the FPGA's gain8 PCM16 conversion from the
same acoustic instant. It does not modify TP4, the validated PCM build, pinout,
GPIO17 input or UART wiring. This diagnostic deliberately does not instantiate
the ENERGY detector or FSM. The LED is a neutral mirror of GPIO17 only and has
no relationship to sample acceptance, conversion or classification.

## Fixed UART protocol v1

Each 95-byte 8-N-1 frame at 1,500,000 baud contains:

| Offset | Bytes | Meaning |
|---:|---:|---|
| 0 | 2 | Sync `A5 C4` |
| 2 | 1 | Version `01` |
| 3 | 1 | Type `21` |
| 4 | 2 | Sequence, u16 little-endian |
| 6 | 4 | Counter of first source LEFT sample, u32 little-endian |
| 10 | 1 | Pair count `16` |
| 11 | 1 | Source stride `2` |
| 12 | 1 | Flags |
| 13 | 80 | 16 × (`RAW24 LE` three bytes + `PCM16 gain8 LE` two bytes) |
| 93 | 2 | CRC-16/CCITT-FALSE over bytes 2..92, little-endian |

Only LEFT is accepted. Every LEFT word advances the source counter; even source
counters are retained, producing 21,093.75 diagnostic pairs/s. Two banks allow
capture to continue while a frame is transmitted. The nominal UART line
utilization is:

`21093.75/16 * 95*10 / 1500000 = 83.49609375%`.

The sustained self-check drives 640 source LEFT samples and decodes every one
of the resulting 20 UART frames (1,900 bytes). It verifies both alternating
banks byte by byte: sequence, first-source counter, flags, all RAW24/PCM16
pairs and each CRC, in addition to requiring zero drop/overrun.

The flags match the existing convention: bit 0 I2S frame error, bit 1 transport
overrun, bit 2 UART RX observed LOW, bit 3 GPIO17 HIGH.

The matching Raspberry parser is
`raspberry_mvp/raw24_diagnostic/safe_field_raw24_protocol.py`.

## Reproduce simulation

```powershell
node verilog_mvp/raw24_capture/sim/run_raw24_capture.mjs
& mvp/evidence/recovery_venv/Scripts/python.exe `
  verilog_mvp/raw24_capture/sim/check_python_contract.py
```

## Reproduce Gowin build

```powershell
& '<GOWIN_INSTALL>/IDE/bin/gw_sh.exe' `
  verilog_mvp/raw24_capture/scripts/build_raw24_capture.tcl
```

Output is isolated under `build/mvp_raw24_capture/`. This task does not program
SRAM or Flash.
