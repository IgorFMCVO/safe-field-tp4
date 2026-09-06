# RAW_I2S_24_CAPTURE — build validation

Result: **PASS** for self-checking simulation, synthesis, place-and-route and
static timing. Hardware programming was **NOT PERFORMED**.

Build timestamp: `2026-09-06T14:29:39-03:00`  
Device: `GW1NSR-4C` / `GW1NSR-LV4CQN48PC6/I5`  
Tool: `Gowin V1.9.11.03 Education`

## Isolation and data path

- This is an additive diagnostic under `verilog_mvp/raw24_capture/`.
- No file under the frozen TP4 RTL was edited.
- Synthesized path: frozen `i2s_clock_gen` → frozen `i2s_rx_24` → paired
  RAW24/gain8 PCM16 packetizer → frozen UART byte transmitter.
- The build source list contains no energy detector and no audio FSM.
- The LED is only a neutral mirror of GPIO17; it neither classifies nor gates
  samples.
- Only valid LEFT samples are counted. Source counters `0,2,4,...` are retained
  (stride 2), with two alternating 16-pair banks.

## Wire contract

One UART 8-N-1 frame contains exactly 95 bytes at 1,500,000 baud:

`A5 C4 | 01 | 21 | seq:u16le | first_source:u32le | 10 | 02 | flags | 16 × (raw24:s24le + pcm16:s16le) | crc:u16le`

The CRC is CRC-16/CCITT-FALSE over bytes 2 through 92 inclusive. For the
independent boundary vector used by both sides, Python produced header
`A5C40121000000000000100224`, numeric CRC `69B9`, wire CRC `B9 69`, and
whole-frame SHA-256
`3D274D76E7BB3B663DD3AC184D05EB3FA66662940D42C16807EE83AB862AAC00`.

The nominal payload/framing utilization is `83.49609375%`. The sustained
physical-rate test sent 640 source LEFT samples, retained 320 samples, emitted
20 packets and decoded all 1,900 UART bytes. For every packet it checked sync,
version/type, sequence `0..19`, first-source counters `0,32,...,608`,
count/stride/flags, all 16 RAW24/PCM16 pairs and CRC. Both alternating banks
were therefore exercised with zero dropped samples and zero overruns.

## Verification

| Gate | Result | Evidence |
|---|---|---|
| Full I2S timing/alignment, LEFT selection, sign and stride | PASS | `simulation.log` |
| 16 RAW24/PCM16 boundary pairs, expected vs actual | PASS | `simulation.log` |
| CRC bytes 2..92 and fixed 95-byte frame | PASS | `simulation.log` |
| Physical-rate two-bank full UART decode | PASS, 20 × 95 bytes, zero loss | `simulation.log` |
| Independent Python golden vector | PASS | `python_contract_vector.log` |
| Raspberry RAW24 host regression | PASS, 9/9 | `python_protocol_tests.log` |
| Synthesis | PASS | `gowin_build_console.log` |
| Place-and-route | PASS | Gowin report and console log |
| Static timing | PASS | setup violations 0; hold violations 0; TNS 0 |
| Hardware programming | NOT PERFORMED | deliberate safety boundary |

The extended sustained test changed testbench/evidence files only. The two
synthesized RAW24 RTL hashes and generated bitstream hash remained unchanged,
so P&R was not rerun for this test-only strengthening.

The corrected Raspberry RAW24 host regression was rerun after the sustained-TB
strengthening and passed all nine tests. No host source was edited by this
validation step.

## P&R and timing

- Logic: `1233/4608` (27%; 1169 LUT, 64 ALU)
- Registers: `1623/3573` (46%; 1622 logic FF, 1 I/O FF)
- CLS: `1674/2304` (73%)
- I/O: `8/39` (21%; 4 input, 4 output)
- Constrained clock: 27.000 MHz
- Actual Fmax: 33.647 MHz
- Worst setup slack: 7.316 ns
- Worst hold slack: 0.708 ns
- Setup TNS: 0.000 ns; violated endpoints: 0
- Hold TNS: 0.000 ns; violated endpoints: 0
- Recovery/removal worst slack: 34.074 ns / 1.884 ns

## Pinout preserved by final P&R report

| Signal | Pin | Direction | I/O |
|---|---:|---|---|
| `sys_clk` | 45 | input | LVCMOS33 |
| `pi_signal` | 40 | input | LVCMOS33 |
| `i2s_sck` | 41 | output | LVCMOS33 |
| `i2s_ws` | 42 | output | LVCMOS33 |
| `i2s_sd` | 43 | input, pull-down | LVCMOS33 |
| `uart_tx` | 39 | output | LVCMOS33 |
| `uart_rx` | 46 | input, pull-up | LVCMOS33 |
| `led` | 10 | output | LVCMOS18 |

## Warnings retained for review

Seven warnings were emitted and none was hidden:

- Six `PA1001` dangling synthesized sum nets (`n7_1_SUM` through
  `n12_1_SUM`) inside the read-only frozen `i2s_rx_24`. The same warning family
  is present in earlier project builds; no timing endpoint is violated.
- One `PR1014` reports generic routing for `sys_clk_d`. It is also present in
  earlier project builds. STA still reports positive setup/hold slack and zero
  TNS. The warning remains visible rather than waived.

No `ERROR` or `FATAL` line appears in the final build console log.

## Reproduction commands

```powershell
node verilog_mvp/raw24_capture/sim/run_raw24_capture.mjs

& mvp/evidence/recovery_venv/Scripts/python.exe `
  verilog_mvp/raw24_capture/sim/check_python_contract.py

& mvp/evidence/recovery_venv/Scripts/python.exe -m unittest -v `
  raspberry_mvp.raw24_diagnostic.test_raw24_protocol

& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gw_sh.exe' `
  verilog_mvp/raw24_capture/scripts/build_raw24_capture.tcl
```

Final bitstream (generated, not programmed):

`build/mvp_raw24_capture/impl/pnr/safe_field_mvp_raw24_capture.fs`

SHA-256:

`B0B665EBB20DAEAB3C3ABCCDCE96858FA8084DCDB1F9B7587EC5EBC72ECF21F1`
