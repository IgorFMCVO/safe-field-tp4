# SAFE-FIELD MVP hardware bridge build summary

Status: **READY FOR PHYSICAL WIRING — NOT PROGRAMMED**.

## Frozen baseline

- The protected I2S, receiver, energy, FSM, GPIO17, TP4 top, TP4 CST and SDC
  files have no diff from commit `9d1f465`.
- `safe_field_tp4_validated.fs` remains unchanged with SHA-256
  `5D8F2D31EF5D0349AC0E52F13AC8A7472FCB1A23103131D13163BB8946F39181`.
- No Gowin Programmer command was executed and neither SRAM nor Flash was
  changed during this phase.

## Protocol and tests

- Protocol v1: 16-byte fixed binary frame, sync `A5 5A`, sequence, FSM state,
  24-bit energy, 32-bit I2S frame counter, flags and CRC-8/ATM.
- UART: 115200 8-N-1; 234 clocks/bit at 27 MHz gives 115384.6 baud (+0.160%).
- RTL testbenches: PASS, 101 checks total (7 UART, 85 protocol, 9 integration).
- Python unit tests: PASS, 5/5.
- Emulator/receiver: PASS; 6 valid frames, one corrupt CRC rejected, one lost
  sequence detected, arbitrary prefix discarded and truncated tail retained.

## Gowin build

- Device: `GW1NSR-LV4CQN48PC6/I5` / `GW1NSR-4C`.
- Tool: Gowin V1.9.11.03 Education. The separate V1.9.12 commercial attempt
  was blocked by its unavailable license and its log was preserved.
- Synthesis: PASS.
- Place & Route: PASS.
- STA: PASS; 0 setup and 0 hold violated endpoints, TNS 0/0, worst setup slack
  +7.781 ns, Fmax 34.181 MHz for the constrained 27 MHz clock.
- Resources: Logic 598/4608 (13%), registers 450/3573 (13%), CLS 465/2304
  (21%), I/O 7/39 (18%).
- Warnings: 8 total. `NL0002` (1) is hierarchy flattening of the trivial
  `rasp_to_tang` wrapper; `PA1001` (6) reports optimized dangling arithmetic
  net endpoints inside the unchanged, physically validated I2S receiver;
  `PR1014` (1) is the existing generic
  route notice for `sys_clk_d`. No warning changes a constrained pin or reports
  a timing violation. The full unfiltered messages remain in the build logs.

Bitstream:

`C:\SAFE-FIELD\fpga\tp4-audio-inmp441\build\safe_field_mvp_hw_bridge\impl\pnr\safe_field_mvp_hw_bridge.fs`

SHA-256:

`2FEE0AE7BFA036DBB1F97EB6CC06A3D2A8FBC8CDD7BAE8E139F450D6E298A963`

## Final pin mapping

| Signal | Package pin | Direction | Electrical result |
|---|---:|---|---|
| `sys_clk` | 45 | input | LVCMOS33, Bank 1 |
| `pi_signal` | 40 | input | LVCMOS33, Bank 1 |
| `uart_tx` | 39 | output | LVCMOS33, Bank 1 |
| `i2s_sck` | 41 | output | LVCMOS33, Bank 1 |
| `i2s_ws` | 42 | output | LVCMOS33, Bank 1 |
| `i2s_sd` | 43 | input | LVCMOS33 pull-down, Bank 1 |
| `led` | 10 | output | LVCMOS18, Bank 0 |

Physical connection required next, with both boards powered off:
Tang package pin 39 / P7 position 6 -> Raspberry GPIO15/RXD0 physical pin 10,
plus the already required shared ground. The DVP camera must remain disconnected.

## Exact verification commands

```powershell
node sim\run-mvp-hw-bridge.mjs
python -m unittest discover -s raspberry\tests -v
python raspberry\uart_emulator.py --output evidence\mvp_hw_bridge\emulator_demo.bin
python raspberry\safe_field_hw_bridge.py --input-file evidence\mvp_hw_bridge\emulator_demo.bin --jsonl evidence\mvp_hw_bridge\emulator_receiver_output.jsonl
python -m py_compile raspberry\safe_field_uart_protocol.py raspberry\safe_field_hw_bridge.py raspberry\uart_emulator.py
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gw_sh.exe' scripts\build_safe_field_mvp_hw_bridge.tcl
Get-FileHash build\safe_field_mvp_hw_bridge\impl\pnr\safe_field_mvp_hw_bridge.fs -Algorithm SHA256
```

Raspberry read-only audit commands:

```bash
pinctrl get 15
ls -l /dev/serial0 /dev/ttyAMA0 /dev/ttyS0
systemctl is-enabled serial-getty@ttyAMA0.service serial-getty@serial0.service
systemctl is-active serial-getty@ttyAMA0.service serial-getty@serial0.service
```
