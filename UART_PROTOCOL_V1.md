# SAFE-FIELD UART telemetry protocol v1

UART electrical/logical settings: 3.3 V LVCMOS, idle HIGH, 115200 baud,
8 data bits, no parity and one stop bit (8-N-1). The FPGA divider uses 234
27 MHz clocks per bit, producing 115384.6 baud (+0.160%). Multibyte integers
are unsigned little-endian.

| Offset | Size | Field | Definition |
|---:|---:|---|---|
| 0 | 2 | sync | `A5 5A` |
| 2 | 1 | version | `01` |
| 3 | 1 | payload length | `0B` |
| 4 | 2 | sequence | increments modulo 65536 |
| 6 | 1 | FSM state | 0=QUIET, 1=ACTIVE |
| 7 | 3 | energy | current unsigned 24-bit window energy |
| 10 | 4 | frame counter | completed relative I2S frames, modulo 2^32 |
| 14 | 1 | flags | status/error bitmap |
| 15 | 1 | CRC | CRC-8/ATM over offsets 2..14 |

Flags: bit 0 latches an I2S frame error; bit 1 latches a telemetry scheduling
overrun; bit 2 confirms that a nonzero sample has been seen; bit 3 reports the
GPIO17 override level. Bits 4..7 are reserved and zero.

CRC parameters are polynomial `0x07`, initial value `0x00`, no reflection and
no final XOR. Frames are emitted once per 256 complete I2S frames, about
164.8 messages/s at 42.1875 kHz. A fixed-size frame takes about 1.39 ms on the
wire, leaving ample margin before the next telemetry event.
