# SAFE-FIELD MVP FPGA to Raspberry bridge

Current gate: **hardware build complete; stopped before physical wiring and FPGA
programming as required**.

- UART protocol v1 is specified in `UART_PROTOCOL_V1.md`.
- FPGA TX, protocol packetizer and frozen audio-path integration are implemented.
- Raspberry parser, JSONL logger, real-time console and UART emulator are under
  `raspberry/`.
- RTL simulation, Python tests, synthesis, P&R and STA are PASS.
- The independent `.fs`, SHA-256, resource use, warnings, pin proof and exact
  commands are recorded in `evidence/mvp_hw_bridge/BUILD_SUMMARY.md`.
- Required next operator action: power down both boards and connect Tang package
  pin 39 / P7 position 6 to Raspberry physical pin 10 (GPIO15/RXD0), preserving
  the shared ground and leaving the camera disconnected.
- Raspberry UART device nodes are currently absent. UART enablement/reboot and
  SRAM programming belong to the next phase, after the physical connection has
  been made and confirmed.
