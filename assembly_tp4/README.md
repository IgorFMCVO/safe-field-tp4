# SAFE-FIELD TP4 — AArch64 and NEON

Target actually used: Raspberry Pi 4 Model B, AArch64. This preserves the
official ARM64 competencies even if another Raspberry model appears in the
course wording.

Implemented in `safe_field_arm64.S`:

- 128-bit multiword addition with `ADDS/ADC`;
- signed integer to IEEE-754 double conversion with `SCVTF`;
- state lookup table;
- masks, logical shift, XOR and 32-bit rotate for protocol mixing;
- exact scalar and 8-lane NEON integer audio-energy reduction;
- scalar and 4-lane NEON floating-point normalization.

Build and test on AArch64 Linux:

```bash
make clean all disassembly
./safe_field_arm64_test 400
python3 test_command_protocol.py
```

`safe_field_bidirectional_test.py` is the physical three-vector acceptance
test. Do not run it until Tang pin 46 has been connected to Raspberry physical
pin 8 with both boards de-energized and the academic FPGA build is in SRAM.
