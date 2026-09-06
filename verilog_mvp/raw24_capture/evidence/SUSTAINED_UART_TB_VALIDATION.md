# RAW24 sustained UART test strengthening

Result: **PASS**. Hardware programming: **NOT PERFORMED**.

The strengthened self-checking testbench validates the entire emitted stream,
not merely internal packet counters:

- 640 LEFT source samples at one sample per 640 system-clock cycles;
- stride 2, yielding 320 retained samples;
- 20 complete frames × 95 bytes = 1,900 UART bytes decoded as 8-N-1 with
  `CLKS_PER_BIT=18`;
- sync `A5 C4`, version `01`, type `21`;
- sequences `0..19`;
- first-source counters `0,32,...,608`;
- count 16, stride 2 and flags zero;
- all 16 signed RAW24 and gain8 PCM16 pairs in every frame;
- CRC-16/CCITT-FALSE over bytes 2..92 in every frame;
- both alternating banks exercised with zero dropped samples and zero overrun.

Command:

```powershell
node verilog_mvp/raw24_capture/sim/run_raw24_capture.mjs
```

Testbench SHA-256:

`1C33EE2BB09FF8D8B155AC8ECD2484959F8BE4F0F707F739122E11F64C6E5353`

Simulation log SHA-256:

`ED52970C12BDEAF98A710C3D525A426B833367656AA00750DBFD61C57A417574`

The synthesized RTL remained byte-identical:

- packet transport:
  `0E9FA45D432761183F9CB12DE18848F7E48566D804995855537E961EECA03B9B`
- diagnostic top:
  `677FAD5E2CB1F3408BC98AA4D38C859AD588191719CADDB40A9AE648592D09A9`

Therefore P&R was not rerun. The existing unprogrammed bitstream remains:

`build/mvp_raw24_capture/impl/pnr/safe_field_mvp_raw24_capture.fs`

SHA-256:

`B0B665EBB20DAEAB3C3ABCCDCE96858FA8084DCDB1F9B7587EC5EBC72ECF21F1`
