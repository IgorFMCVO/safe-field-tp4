# P0 audio sensitivity — physical session log

Date: 2026-09-06
Branch: `mvp-occurrence-recovery-ptbr-physical`
Pre-hardware checkpoint: `550b819`
Baseline C: **PAUSED**
Speaker playback/volume increase: **NOT PERFORMED**

## Pre-SRAM gates

- Frozen TP4 diff: none.
- RAW24 host protocol tests: 9/9 PASS.
- SNR/calibration tests: 11/11 PASS.
- Affected regression: 52/52 PASS.
- Sustained RTL UART test: 20 frames x 95 bytes = 1,900 bytes, all fields,
  samples and CRC checked, zero drop/overrun.
- Independent review: GO for RAW24 SRAM diagnostic.
- Bitstream SHA-256:
  `B0B665EBB20DAEAB3C3ABCCDCE96858FA8084DCDB1F9B7587EC5EBC72ECF21F1`.

## JTAG scan

Command:

```powershell
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\Programmer\bin\programmer_cli.exe' --scan --cable-index 1
```

Result:

```text
Target Cable: Gowin USB Cable(FT2CH)/0/None/null@2.5MHz
Family: GW1NSR
Name: GW1NSR-4C
ID: 0x0100981B
1 device(s) found
exit_code=0
```

Before programming, Raspberry `/dev/serial0` had no process owner and GPIO17
was `output LOW`.

## SRAM programming

Command:

```powershell
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\Programmer\bin\programmer_cli.exe' `
  --device GW1NSR-4C --operation_index 2 --frequency 2.5MHz `
  --fsFile 'C:\SAFE-FIELD\fpga\tp4-audio-inmp441\build\mvp_raw24_capture\impl\pnr\safe_field_mvp_raw24_capture.fs' `
  --cable-index 1
```

Result:

```text
Target Device: GW1NSR-4C(0x0100981B)
Operation "SRAM Program" for device#1
Programming: 100%
User Code: 0x000049F3
Status Code: 0x0003F020
Finished
exit_code=0
```

No Flash operation was performed.

## Sequential RAW24 silence capture

Capture ID: `39f58c32-f41a-426a-838c-5af27ee46929`
UTC start: `2026-09-06T17:51:04.459877+00:00`
Wall duration: `12.028768306976417 s`
Samples: `253168` at diagnostic rate `21093.75 sample/s`

| Measurement | RAW24 A | UART/WAV PCM16 B/C |
|---|---:|---:|
| min | -49234 | -1539 |
| max | 37006 | 1156 |
| peak | 49234 | 1539 |
| RMS including DC | 12727.536153 | 397.734297 |
| DC | 49.484706 | 1.077672 |
| AC RMS / standard deviation | 12727.439954 | 397.732837 |
| unique samples | 32029 | 2604 |
| zero / non-zero | 20 / 253148 | 218 / 252950 |
| p95 absolute | 25070 | 784 |
| p99 absolute | 33094 | 1034 |

Transport and boundaries:

- valid UART frames: `15823`;
- CRC/format/pre-lock candidate/resync errors: `0`;
- sequence/source losses and discontinuities: `0`;
- FPGA I2S frame error/transport overrun packets: `0`;
- RAW24 to PCM16 mismatches: `0`;
- PCM16 saturated samples: `0`;
- observed A-to-B normalized gain: `7.999975707x`, `18.061773 dB`;
- UART PCM payload to WAV payload: byte-identical, `0 dB`;
- capture gate: `PASS`.

Artifact hashes:

```text
352C1BB9C9DAE871A37CDD4972A5AC4D4BDD5A8262DC859EED2ABDF0F6B522F0  p0_raw24_silence_20260906T1752Z.s24le
A0629BC1F5625C0695BE292333D28EA000F58AA804B3DAD1B9F00C25B609CE7F  p0_raw24_silence_20260906T1752Z_pcm16.wav
E489F524ECC791A9C8B884614E9E5522DACEEA437303D81AC9590674731A02F2  p0_raw24_silence_20260906T1752Z.csv
19A2BBB05829C228095BC4D912027879C19DB22D2A7F9558BA1F1FC03BA3BD47  p0_raw24_silence_20260906T1752Z_report.json
```

The next step is one moderate acoustic capture, only after the operator confirms
that the microphone acoustic port is unobstructed and its face is not touching
a surface. No threshold, VAD, energy FSM or volume compensation participates.

## Operator physical validation

The operator replied `pronto` after the single requested check: the acoustic
port was free and the module face was not touching a surface. No wire, supply
or powered connection was changed.

## First signal attempt — excluded

The first 18-second signal attempt is preserved but **not accepted**. The
bit-at-a-time Python CRC parser could not continuously consume the 1.5 Mbaud
stream under the instantaneous Raspberry load. It recorded 311056 samples,
one CRC error, three lost packets/96 source samples and an out-of-tolerance
sample rate. Its acoustic values are not used as acceptance evidence.

The diagnostic-only parser was changed from the mathematically correct Python
bit loop to the equivalent CPython C implementation:

```python
binascii.crc_hqx(payload, 0xFFFF)
```

The fixed RTL golden frame remained byte-identical: wire CRC `B9 69`, frame
SHA-256 `3D274D76E7BB3B663DD3AC184D05EB3FA66662940D42C16807EE83AB862AAC00`.
On the Raspberry the new parser sustained `16.641 Mbit/s`, `11.09x` the
required 1.5 Mbaud input rate.

## Transport recheck after parser fix

A 12-second no-playback recheck then produced 253168 samples and 15823 packets
with zero CRC, format, sequence, source-counter, frame and overrun errors.
Capture gate: **PASS**.

## Valid moderate signal capture

- Capture ID: `97ebbc74-690c-4ba1-9501-8deff545b91e`.
- Capture: `2026-09-06T17:58:12.478628Z`, 18.023535 s wall time.
- Explicit output: `Speakers (Realtek(R) Audio)`, Windows DirectSound device 9.
- Endpoint scalar: `0.08000000566244125`, unmuted, **unchanged**.
- Playback: `2026-09-06T17:58:19.247792Z` to
  `2026-09-06T17:58:27.072777Z`.
- Stimulus: `mvp/generated_audio/A_conflict_four_speakers/segment_001.wav`.
- Stimulus duration: 7.045 s; source peak 11066 PCM16; clipped samples 0.
- Capture samples: 380096; valid packets: 23756.
- CRC, format, sequence/source loss, I2S frame errors and overrun: all `0`.
- RAW24-to-PCM16 mismatches: `0`; saturated PCM16 samples: `0`.
- UART PCM payload and WAV payload: byte-identical.

Whole valid capture:

| Measurement | RAW24 A | UART/WAV PCM16 B/C |
|---|---:|---:|
| min | -28760 | -899 |
| max | 22406 | 700 |
| peak | 28760 | 899 |
| RMS including DC | 7828.894268 | 244.662314 |
| DC | -134.188631 | -4.661791 |
| AC RMS / standard deviation | 7827.744175 | 244.617897 |
| unique samples | 22452 | 1523 |
| zero / non-zero | 35 / 380061 | 569 / 379527 |
| p50 absolute | 4332 | 135 |
| p95 absolute | 17374 | 543 |
| p99 absolute | 22542 | 705 |

Guarded playback window, 7.0 to 14.3 seconds from capture start:

| Measurement | RAW24 A | UART/WAV PCM16 B/C |
|---|---:|---:|
| samples | 153985 | 153985 |
| min | -28104 | -879 |
| max | 22406 | 700 |
| peak | 28104 | 879 |
| RMS including DC | 7940.666300 | 248.170594 |
| DC | -385.094467 | -12.502965 |
| AC RMS | 7931.322928 | 247.855441 |
| p95 absolute | 17886 | 559 |
| p99 absolute | 23142 | 724 |

The same-capture pre-playback AC RMS was 8563.474906 RAW24 / 267.607873
PCM16. Playback/pre ratios were therefore `0.926180x` and `0.926189x`: there
was no amplitude increase at checkpoint A. Against the independent silence
reference, whole-capture AC ratios were `0.615029x` RAW24 and `0.615031x`
PCM16 (`-4.222 dB`). The fail-closed comparison result is **FAIL —
NO_CLEAR_UNSATURATED_ACOUSTIC_RESPONSE**.

The DC-rejected 300–3400 Hz PCM16 RMS values were 20.8242 before playback,
20.8588 during playback and 20.9396 after playback. Conservative noise uses
the maximum of pre/post. Since measured playback power did not exceed that
noise power, the audited SNR function correctly returned no finite SNR rather
than a fictitious negative/extreme value.

## Boundary decision

- A→B: no loss; normalized gain `8.000306x` / `+18.062132 dB`, matching the
  documented diagnostic gain8 mapping.
- B→C: no loss; UART PCM bytes equal WAV payload bytes, `0 dB`.
- The amplitude anomaly is already present at **A = FPGA RAW24**, before PCM
  conversion, UART, WAV, filtering, VAD, energy and FSM.
- Classification: **E — MICROPHONE SUSPECT**, specifically the acoustic
  transducer/port side of the module. This is an isolation result, not a claim
  that the I2S digital interface is dead: SD remains dynamic and error-free.
- Independent review confirmed the classification. Its speech-band check found
  playback/pre-playback `0.99661x` (`-0.0295 dB`), so there was no detectable
  acoustic modulation even after excluding sub-300 Hz drift.
- BASELINE C remains paused. The next action requires powered-off physical
  substitution/comparison with a known-good INMP441; no further volume increase
  is justified.

## Direct live-voice retest requested by operator

The operator requested a short direct voice test. Two initial windows were
excluded because each lost one UART packet. A final six-second capture pinned
to one Raspberry CPU was valid:

- label: `p0_raw24_voice_quick_final_20260906T181404Z`;
- capture ID: `2b5b4982-f67c-49d3-bf10-859bf74e1b7d`;
- 126912 samples / 7932 packets;
- CRC, format, sequence/source loss, frame error and overrun: all `0`;
- RAW24 RMS / AC RMS: `8080.277862` / `8079.367134`;
- PCM16 RMS / AC RMS: `252.516188` / `252.480275`;
- RAW24 voice/silence AC ratio: `0.634799x` (`-3.947274 dB`);
- PCM16 voice/silence AC ratio: `0.634799x` (`-3.947280 dB`);
- RAW24→PCM16 mismatches: `0`; UART→WAV byte-identical;
- result: **FAIL — NO_CLEAR_UNSATURATED_ACOUSTIC_RESPONSE**.

Remote Raspberry evidence hashes:

```text
694B6701E5B1275EB087E11399FB9F68C68956C6C6B50544EF99EF19365FE1AA  p0_raw24_voice_quick_final_20260906T181404Z.s24le
7D2CA425195E65B783B6B80B68044D65E5BACDBE121C8CFED09C49DDEC5338937  p0_raw24_voice_quick_final_20260906T181404Z_pcm16.wav
C1F2B293E073A1562812D186C3681CD85D36CF4DDDF204AA91ED5B3FACD85BF4  p0_raw24_voice_quick_final_20260906T181404Z.csv
9556656AB7110AABBB66874A451991AD804750BF4B68A39FDF419A4666D49360  p0_raw24_voice_quick_final_20260906T181404Z_report.json
4C93BF3C305479AF692E792D68A7A8705889CC889C60A8CF5656AA75A8D9492C  p0_raw24_voice_quick_final_20260906T181404Z_comparison.json
```

This live-voice retest confirms rather than changes the prior isolation:
digital transport and amplitude preservation pass, while no acoustic response
appears at FPGA RAW24 checkpoint A.
