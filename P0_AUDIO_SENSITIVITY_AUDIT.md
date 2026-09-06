# P0_AUDIO_SENSITIVITY_ANOMALY — root-cause audit

Date: 2026-09-06
Branch: `mvp-occurrence-recovery-ptbr-physical`
Frozen TP4 changed: **NO**
Flash programmed: **NO**
Baseline C: **PAUSED**

## Decision

The low apparent sensitivity is not caused by I2S decoding, signed conversion,
UART scaling, WAV generation or the SNR calculation. The anomaly is present in
the FPGA's raw signed 24-bit samples before all those stages.

**Root-cause classification: E — MICROPHONE SUSPECT**, localized to the
physical/acoustic transducer side of the INMP441 module. The digital interface
is alive: SD is dynamic, LEFT samples arrive at the exact rate, and the valid
capture has zero frame, CRC, sequence or overrun errors. This classification
does not claim that the complete module is digitally dead or prove the MEMS
die alone is defective; module, solder and local supply remain in the same
physical locus. An independent evidence review reached the same classification.

## Required result matrix

| Gate | Result | Evidence |
|---|---|---|
| I2S format | PASS | 24-bit signed two's-complement, MSB first, 32 clocks/slot, 64/frame |
| I2S alignment | PASS | delay index 0 excluded; indices 1–24 captured; signed LEFT and RIGHT poison tests exact |
| sample24 deterministic levels | PASS | exact positive/negative values at -80, -60, -50, -40, -30, -20 and -6 dBFS |
| PCM16 conversion | PASS | `clamp_signed16(sample24 >>> 5)`, explicit saturation; exact for every injected level |
| UART amplitude | PASS | every paired RAW24/PCM16 sample exact; 0 mismatches |
| WAV amplitude | PASS | UART PCM payload and Pi WAV payload byte-identical; 0 dB |
| SNR calculator | PASS | same PCM16 domain/rate/windows; DC-rejected band; below-noise power returns no finite SNR |

Detailed deterministic evidence:

- `verilog_mvp/i2s_pcm_uart_level_diagnostic/evidence/I2S_PCM_UART_LEVEL_AUDIT.md`
- `verilog_mvp/i2s_pcm_uart_level_diagnostic/evidence/simulation.log`
- `verilog_mvp/i2s_pcm_uart_level_diagnostic/evidence/pi_decode.log`
- `verilog_mvp/raw24_capture/evidence/simulation.log`
- `verilog_mvp/raw24_capture/evidence/SUSTAINED_UART_TB_VALIDATION.md`

The sustained test decoded all `20 x 95 = 1900` UART bytes, sequence 0–19,
source counters 0–608, every RAW24/PCM16 pair and every CRC, with no drops or
overrun. The complete affected host regression passed 52/52 tests.

## I2S timing audit

- `SCK = 27 MHz / (2 x 5) = 2.700 MHz`.
- `WS = 2.700 MHz / 64 = 42.1875 kHz`.
- WS changes on the falling SCK edge preceding delay index 0.
- The MSB is sampled at index 1, one I2S clock after the WS boundary.
- Exactly 24 bits, indices 1 through 24, are shifted MSB first.
- `sample_valid` is one `sys_clk` pulse at index 24.
- `sample_channel=0` is LEFT, matching physical L/R=GND.
- Negative, positive, minimum and maximum signed samples decode exactly.

The physical capture corroborates a live, aligned stream: 380096 retained LEFT
samples in 18.0235 seconds, zero I2S frame-error packets, and both signs with
22452 distinct RAW24 values. A one-bit-early error would lose the sign under the
SD pull-down; that is not observed. A one-bit-late error would double rather
than suppress amplitude and is excluded by the deterministic delay/padding
poison test.

## Exact 24→16 formula

The additive diagnostic deliberately uses:

```text
shifted = arithmetic_signed(sample24) >>> 5
PCM16   = clamp(shifted, -32768, +32767)
```

It retains the most significant signed information plus three more lower bits
than the original `sample24[23:8]` transport. Thus it is a documented 8x
normalized gain (`+18.0618 dB`), not a gain reduction. The physical valid
signal capture measured `8.000306x` / `+18.062132 dB` and zero mismatches.
There is no second shift, LSB extraction, unsigned conversion or normalization.

## Physical RAW24 checkpoints

The operator confirmed the acoustic port was free and the module face was not
touching a surface. The explicit Windows DirectSound output was
`Speakers (Realtek(R) Audio)`, device 9, unmuted. Endpoint scalar remained at
`0.08000000566244125`; it was not increased. The 7.045-second source WAV had
zero clipped samples.

| Metric | Silence reference | Valid playback capture | Guarded playback window |
|---|---:|---:|---:|
| RAW24 count | 253168 | 380096 | 153985 |
| min | -49234 | -28760 | -28104 |
| max | 37006 | 22406 | 22406 |
| peak | 49234 | 28760 | 28104 |
| RMS including DC | 12727.536153 | 7828.894268 | 7940.666300 |
| DC | 49.484706 | -134.188631 | -385.094467 |
| AC RMS | 12727.439954 | 7827.744175 | 7931.322928 |
| absolute p50 | 7420 | 4332 | 4188 |
| absolute p95 | 25070 | 17374 | 17886 |
| absolute p99 | 33094 | 22542 | 23142 |
| zero/non-zero | 20/253148 | 35/380061 | 13/153972 |
| frame/CRC/sequence errors | 0/0/0 | 0/0/0 | 0/0/0 |

The fail-closed independent-capture ratio is:

```text
RAW24 signal/silence AC = 0.615028961x = -4.222089 dB
PCM16 signal/silence AC = 0.615030680x = -4.222064 dB
```

Within the valid signal capture, playback/pre-playback AC ratios are 0.926180x
at RAW24 and 0.926189x at PCM16. There is therefore no measurable amplitude
increase at checkpoint A. The signal is not being attenuated downstream; it is
absent before checkpoint B.

The whole-band 0.615x ratio is influenced by energy below 300 Hz and is not
interpreted as acoustic attenuation. An independent 300–3400 Hz check measured
playback/pre-playback `0.99661x` (`-0.0295 dB`) and full-signal/silence
`1.00625x` (`+0.054 dB`): effectively no acoustic modulation in the speech
band either.

## Three amplitude boundaries

| Boundary | Measured transfer | Result |
|---|---:|---|
| A FPGA RAW24 → B FPGA/UART PCM16 | `8.000306x`, `+18.062132 dB`, 0 mismatches | PASS, no loss |
| B PCM16 → UART decoding | exact signed little-endian payload | PASS, no loss |
| UART decoded PCM16 → C Raspberry WAV | byte-identical hashes, `1.0x`, `0 dB` | PASS, no loss |

## SNR audit and physical result

Noise and signal are measured in the same signed PCM16 domain, same 21094 Hz
WAV, same scale, and guarded windows. A fourth-order 300–3400 Hz band-pass
rejects DC. Conservative noise is the greater of the pre/post windows.

```text
pre-playback band RMS  = 20.8242217 PCM16
playback band RMS      = 20.8588435 PCM16
post-playback band RMS = 20.9395802 PCM16
noise reference        = 20.9395802 PCM16
```

Because playback power is not greater than noise power,
`sqrt(playback^2 - noise^2)` is zero and SNR is intentionally `null`/not
estimable. The calculator does not compare normalized PCM to raw integers,
does not include DC as signal, and does not invent an extreme negative SNR.

## Diagnostic collector correction

The first signal attempt is preserved and rejected: the original Python
bit-at-a-time CRC fell behind 1.5 Mbaud and produced one CRC error and three
lost packets. Only the additive diagnostic parser was changed to
`binascii.crc_hqx(payload, 0xFFFF)`, which is bit-identical to the RTL golden
CRC. Raspberry benchmark: 16.641 Mbit/s, 11.09x required throughput. A new
12-second transport recheck and the final 18-second capture both passed with
zero errors. No RTL, amplitude mapping, TP4 file or FPGA bitstream changed.

## Evidence and next action

Raw/CSV/WAV/JSON artifacts are preserved on both hosts under:

- Raspberry: `/home/safe-field/p0-raw24-diagnostic/evidence/`
- Razer: `mvp/evidence/occurrence_recovery/p0_audio_sensitivity/`

The SRAM bitstream is
`build/mvp_raw24_capture/impl/pnr/safe_field_mvp_raw24_capture.fs`, SHA-256
`B0B665EBB20DAEAB3C3ABCCDCE96858FA8084DCDB1F9B7587EC5EBC72ECF21F1`.

`P0_AUDIO_SENSITIVITY_ANOMALY` is **RESOLVED_TO_HARDWARE_SUSPECT**, but not
physically repaired. Baseline C must remain paused. The next action is external: with
power removed, compare or replace the INMP441 module with a known-good unit
while preserving the already-validated pinout. Do not compensate by increasing
speaker volume.

## Direct operator-voice confirmation

At the operator's request, a final six-second live-voice capture was run without
speaker playback or volume changes. Capture
`2b5b4982-f67c-49d3-bf10-859bf74e1b7d` retained 126912 samples / 7932 packets
with zero CRC, sequence, source-counter, frame and overrun errors. RAW24 AC RMS
was `8079.367134`, versus `12727.439954` for the silence reference: `0.634799x`
or `-3.947274 dB`. The direct voice test therefore also produced
`NO_CLEAR_UNSATURATED_ACOUSTIC_RESPONSE` and independently reinforces the same
physical/microphone-suspect classification.
