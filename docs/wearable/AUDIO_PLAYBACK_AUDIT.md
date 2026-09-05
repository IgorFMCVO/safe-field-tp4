# Wearable audio playback audit

Date: 2026-09-05

The official Waveshare schematic V1.0 and Arduino example confirm the wearable
audio output path: ESP32-S3 I2S drives the ES8311 codec; the analog output enters
the NS4150 power amplifier; GPIO46 enables the amplifier; and the amplified
output terminates at the `SPK` connector.

The diagnostic firmware therefore uses the official mapping and driver:

| Signal | ESP32-S3 GPIO |
|---|---:|
| I2S MCLK | 16 |
| I2S BCLK | 41 |
| I2S LRCK | 45 |
| I2S DOUT | 40 |
| I2S DIN | 42 |
| I2C SDA / SCL | 15 / 14 |
| PA enable | 46 |

Sources audited:

- `tools/waveshare-esp32-s3-touch-amoled-2.06-official/Schematic/ESP32-S3-Touch-AMOLED-2.06-Schematic-V1.0.pdf`
- `tools/waveshare-esp32-s3-touch-amoled-2.06-official/examples/arduino/08_ES8311/08_ES8311.ino`
- official repository commit `b099739ad0e33b34e5fbaae77f02bd84805d79a3`

Physical/software boundary results:

- ES8311 initialization through I2C: PASS.
- PCM write count through ESP_I2S: PASS, all expected bytes accepted.
- Physical sound pressure at the remote INMP441: FAIL / not observed
  reproducibly in the FPGA telemetry.

This result does not prove a codec failure. It isolates the unverified boundary
to the transducer/amplifier/acoustic path after the digital I2S write. The likely
causes are an absent or disconnected speaker transducer, a PA-to-SPK path issue,
or insufficient fixed acoustic coupling. No hardware was changed.
