# INMP441 acoustic revalidation — 2026-09-13

## Outcome

`PHYSICAL_ACOUSTIC_CAPTURE = PASS`

The frozen TP4 RTL was not changed. The Tang remained programmed in SRAM with the temporary RAW24 diagnostic image. Capture was armed and valid UART frames were confirmed before the Tang LED and wearable were changed from `AUDIO_QUIET` to `AUDIO_ACTIVE`; the acoustic stimulus only occurred after those acknowledgements.

## Human-voice capture

- Capture: `20260913T182352611417Z_30f316ae`
- RAW24 samples: 949,168; non-zero: 852,987.
- RAW24 RMS/peak: 116,455.53 / 1,018,192.
- I2S frame errors: 0.
- UART CRC errors / sequence losses: 3 / 3 over 59,323 frames. These three transport discontinuities make the whole-file transport gate fail, but do not erase the independently observed acoustic content.
- A speech-like interval appeared around 9.5–20.5 s, with dominant components between approximately 94 and 562 Hz and up to 79.5% of spectral energy in 80–4,000 Hz.
- Local `faster-whisper-large-v3-turbo` transcribed the derived 80–3,400 Hz interval as: “Alô, teste, teste, captura de áudio, teste de som, teste de áudio, teste de som, captura de áudio, teste, teste de captura, teste de...”
- Original PCM16 SHA-256: `05D16F70F45F0AB3FD1B30CD56C422FAC347E871ECC1E6D4097E291B7DE82AA7`.
- Derived speech-window SHA-256: `CE60089B9B57BB3BFDA6E6400117F3D14C86E2B4FFEF13D5AF7ECA584C4E93D8`.

The transcription is secondary evidence because no expected phrase was supplied to the ASR. It is nevertheless coherent speech recovered exclusively from Tang/Raspberry PCM, not from the notebook microphone.

## Synchronized notebook-speaker capture

- Capture: `20260913T182731032013Z_ac61a1df`.
- Stimulus: 1,000 Hz, digital peak 0.30, Windows endpoint 0.35; the original endpoint level was restored automatically.
- Capture was already receiving RAW24 for 3.70 s before playback began.
- Expected tone window: 4.9–8.4 s after the first captured sample.
- Dominant received frequency in that window: **1,000.0 Hz**.
- 1 kHz bin / local spectral median: **169.46×** during the tone, versus 0.65× before and 1.14× after.
- Valid transport frames: 31,646.
- CRC errors / sequence losses / I2S frame errors: **0 / 0 / 0**.
- RAW24 samples: 506,336; non-zero: 453,074; RMS/peak: 81,625.67 / 721,440.
- PCM16 SHA-256: `FF97DCC2DBEEF0C3052FAA295685F1F2B21B2410C7948C66F8C1ABCCAC3549D3`.
- Synchronization log SHA-256: `C68E5F52F56A995BF168666D7307A8C2E24F4429F11485D6B8AB30F2A65C23C4`.

The notebook microphone witness did not meet its own RMS gate, so it is not used as evidence. The sensor under test did show the exact injected frequency in the correct synchronized window.

## Root cause and disposition

Before the microphone ground joint was repaired, the same direct digital monitor saw zero SD highs. After the operator resoldered the ground connection and measured a stable 0.6 ohm path (0.3 ohm probe baseline), SD activity returned. The post-repair acoustic tests now demonstrate both intelligible human speech and an exact synchronized 1 kHz response.

The evidence is therefore most consistent with an intermittent physical microphone harness/ground contact in the earlier runs, compounded by poorly synchronized/low-level playback tests. It is not consistent with a current I2S decoder, PCM scaling, or INMP441 conversion failure.

Final state: Raspberry phase `quiet`, wearable `AUDIO_QUIET`, capture stopped. No hardware connection or frozen TP4 artifact was changed by this revalidation.
