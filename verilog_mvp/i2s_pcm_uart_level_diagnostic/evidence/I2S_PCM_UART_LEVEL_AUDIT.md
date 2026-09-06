# P0 audio sensitivity anomaly — deterministic RTL audit

Date: 2026-09-06  
Scope: simulation and read-only RTL inspection only  
Hardware programming: **NOT PERFORMED**  
Frozen TP4 RTL modified: **NO**

## Result

**PASS.** The deterministic chain preserves signed samples through:

`I2S SD -> one-bit delay -> signed sample24 -> saturate(sample24 >>> 5) -> PCM16 LE -> UART -> CRC`

The test resolves samples down to -80 dBFS. Therefore the observed physical
acoustic sensitivity anomaly is not explained by a decoder bit alignment,
sign-extension, LEFT selection, gain8 quantization, UART byte order or CRC bug.

## Timing and channel audit

- With `HALF_PERIOD_CLKS=5`, SCK is `27 MHz / (2*5) = 2.700 MHz`.
- There are exactly 32 SCK clocks per slot and 64 per frame, so WS is
  `2.700 MHz / 64 = 42.1875 kHz`.
- WS changes on the falling SCK edge before slot index 0.
- Index 0 is the mandatory I2S one-clock delay and is deliberately poisoned by
  the testbench.
- Indices 1 through 24 are shifted MSB first. Indices 25 through 31 are padding
  and are also deliberately poisoned.
- SD is changed on falling SCK and observed by the receiver one 27 MHz clock
  after rising SCK, during the stable high phase.
- `slot_channel` captures WS at index 0; `sample_channel=0` is LEFT. The test
  injects a distinct RIGHT poison word and proves that the UART transport
  rejects every RIGHT sample.
- `sample_valid` is asserted only when index 24 completes the signed word and
  is verified as a one-`sys_clk` pulse.
- No `frame_error` was observed.

## Exact conversion

The diagnostic amplitude for each requested level is:

`A24 = round((2^23 - 1) * 10^(dBFS/20))`

The implemented gain8 mapping is:

`PCM16 = clamp(sample24 >>> 5, -32768, 32767)`

Arithmetic right shift rounds negative two's-complement values toward negative
infinity; the one-count positive/negative asymmetry at small levels is expected.
Compared with the original `sample24[23:8]` mapping, shifting by 5 instead of 8
is exactly `8x`, or `+18.0618 dB`, before saturation. Saturation begins at about
-18.0618 dBFS input.

| Level | sample24 + | PCM16 expected/actual + | sample24 - | PCM16 expected/actual - |
|---:|---:|---:|---:|---:|
| -80 dBFS | 839 | 26 / 26 | -839 | -27 / -27 |
| -60 dBFS | 8,389 | 262 / 262 | -8,389 | -263 / -263 |
| -50 dBFS | 26,527 | 828 / 828 | -26,527 | -829 / -829 |
| -40 dBFS | 83,886 | 2,621 / 2,621 | -83,886 | -2,622 / -2,622 |
| -30 dBFS | 265,271 | 8,289 / 8,289 | -265,271 | -8,290 / -8,290 |
| -20 dBFS | 838,861 | 26,214 / 26,214 | -838,861 | -26,215 / -26,215 |
| -6 dBFS | 4,204,263 | 32,767 / 32,767 SAT | -4,204,263 | -32,768 / -32,768 SAT |

The first 14 values are repeated as necessary to form one complete 32-sample
packet.

## UART packet proof

- Sync: `A5 C3`
- Version: `01`
- Type: `20` (`PCM_S16_LE`)
- Packet sequence: `0`
- First sample counter: `0`
- Sample count: `32`
- Flags: `0x24`
- Payload: all 32 signed PCM16 values match independently computed expected
  values, decoded little-endian.
- CRC-16/CCITT-FALSE expected: `D90A`
- CRC-16/CCITT-FALSE actual: `D90A`
- Accepted samples: `32`
- Dropped samples: `0`
- Transport overrun: `0`

## Immutable source hashes used by the simulation

| SHA-256 | Source |
|---|---|
| `57D1CA1648D425E8971ECDF4A8028337FEE1B6C18C20955AA3CF27320FA00BC0` | `verilog_tp4/rtl/frozen_baseline/i2s_clock_gen.v` |
| `F093FD39DEE74F1AF3FAF10F58CD811C02B30ED5096596C364C5F87BC05EE07C` | `verilog_tp4/rtl/frozen_baseline/i2s_rx_24.v` |
| `7F0CB30AC3C12A060FBC893B7DAE2BE5FF2E3EB9C9365EA95E342D4F5711EA34` | `verilog_tp4/rtl/frozen_baseline/uart_tx_byte.v` |
| `BBDC5339794E1101F5F0E5BE2EDC85BA2C19CC9EE4643E0259EA5032A2695EAB` | `verilog_mvp/pcm_stream/rtl/safe_field_pcm_packet_tx.v` |
| `9F036127F8AAC317E7CF825EDE8C02ED30BBE66E88AFA15F27B534E9147DC4D5` | `verilog_mvp/pcm_stream_gain8/rtl/safe_field_pcm_s24_to_s16_sat.v` |
| `6D2DF07DF043C8945272DE98F5E40DEEE40BAD8A341929ED075F1E8EE60000C2` | `verilog_mvp/pcm_stream_gain8/rtl/safe_field_pcm_packet_tx_gain8.v` |

## Reproduction

```powershell
node verilog_mvp/i2s_pcm_uart_level_diagnostic/sim/run_i2s_pcm_uart_level_diagnostic.mjs
```

Machine-readable/raw simulator evidence:
`verilog_mvp/i2s_pcm_uart_level_diagnostic/evidence/simulation.log`.
