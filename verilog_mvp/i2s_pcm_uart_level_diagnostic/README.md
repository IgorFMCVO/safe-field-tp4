# I2S -> PCM16 -> UART level diagnostic

This is an additive simulation-only diagnostic. It references the frozen I2S
receiver and UART byte transmitter without modifying them. It does not contain
a Gowin build script and must not be used to program hardware.

The self-checking test drives complete 64-clock I2S frames (32 clocks per
slot), including the mandatory one-clock I2S delay, 24 signed MSB-first data
bits and padding. LEFT carries deterministic positive and negative amplitudes
at `-80, -60, -50, -40, -30, -20, -6 dBFS`; RIGHT carries a poison value and
must never enter the UART payload.

The expected conversion is computed independently in the testbench:

`pcm16 = saturate_s16(sample24 >>> 5)`

The `>>> 5` conversion is gain 8 relative to the original `sample24[23:8]`
transport. A complete UART_PCM16_V1 packet is decoded and checked for header,
version, type, sequence, first-sample counter, flags, 32 little-endian PCM16
samples and CRC-16/CCITT-FALSE.

Run from the repository root:

```powershell
node verilog_mvp/i2s_pcm_uart_level_diagnostic/sim/run_i2s_pcm_uart_level_diagnostic.mjs
python -m verilog_mvp.i2s_pcm_uart_level_diagnostic.sim.verify_pi_decode
```

The generated evidence is written to `evidence/simulation.log` and
`evidence/pi_decode.log` in this directory. The second command feeds the exact
UART frame emitted by the HDL simulation to the production Raspberry decoder.
