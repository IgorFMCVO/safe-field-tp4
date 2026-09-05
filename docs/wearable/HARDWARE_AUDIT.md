# SAFE-FIELD wearable hardware audit

Date: 2026-09-04

## Identified device

| Item | Verified result |
|---|---|
| Product | Waveshare ESP32-S3-Touch-AMOLED-2.06 |
| Windows port | `COM7`, native USB serial |
| USB | `VID_303A:PID_1001`, USB Serial/JTAG composite device |
| MCU | ESP32-S3 QFN56 rev. 0.2, dual core, Wi-Fi/BLE |
| PSRAM | 8 MB embedded OPI PSRAM reported by esptool |
| Flash | 32 MB detected by esptool; firmware build follows Waveshare CI's 16 MB partition profile |
| Display | 2.06 inch, 410 x 502, QSPI CO5300 |
| Touch | FT3168 capacitive, I2C address `0x38`, interrupt GPIO38 |
| Power/Battery | AXP2101 PMIC; battery presence and percentage are readable |
| Vibration | Motor net documented on GPIO18; short edge-triggered pulse only |
| Wi-Fi | ESP32-S3 2.4 GHz Wi-Fi; used for HTTP polling |

## Pin references used by the firmware

| Function | GPIO |
|---|---:|
| CO5300 QSPI D0/D1/D2/D3 | 4/5/6/7 |
| CO5300 SCLK/CS/RESET | 11/12/8 |
| I2C SDA/SCL | 15/14 |
| Motor | 18 |

The values above come from the official Waveshare `pin_config.h` and schematic
V1.0. Touch was audited but is intentionally not part of Sprint 01.

## Official BSP and examples

- Product/wiki: <https://www.waveshare.com/wiki/ESP32-S3-Touch-AMOLED-2.06>
- First-party sources: <https://github.com/waveshareteam/ESP32-S3-Touch-AMOLED-2.06>
- Audited first-party commit: `b099739ad0e33b34e5fbaae77f02bd84805d79a3`
- Arduino display baseline: `examples/arduino/01_HelloWorld`
- Battery baseline: `examples/arduino/05_LVGL_AXP2101_ADC_Data`
- ESP-IDF managed component: `waveshare/esp32_s3_touch_amoled_2_06`
- Local build core: Arduino-ESP32 `3.3.11`, matching the first-party CI.

## Original firmware recovery

No erase or upload was attempted before a recovery route was identified.
The official repository contains:

`FirmWare/ESP32-S3-Touch-AMOLED-2.06-xiaozhi-251104.bin`

Official recovery SHA-256:

`877FB298B60BD0623151856720BF262038C427A8CF840B9587DEF2231C712AC5`

An additional full-flash read was attempted before SAFE-FIELD programming, but
the native USB transfer stopped at 7%; the incomplete artifact is not valid as
a backup and must not be used. The immutable official recovery image above is
the verified restoration route.

## Scope decision

Sprint 01 uses the display, battery telemetry, Wi-Fi, HTTP polling, and the
documented motor. Camera, touch UI, onboard audio, Bluetooth, AI, transcription,
and WebSocket are out of scope.

## Physical result

- ESP32-S3 application compiled and uploaded on COM7 with segment hash
  verification.
- Operator visually confirmed the SAFE-FIELD boot screen.
- AXP2101 initialization reported PASS on the physical board.
- The board joined the 2.4 GHz WLAN and received the existing Core endpoint by
  HTTP 200.
- A single GPIO18 vibration pulse occurred only on the recorded
  `AUDIO_QUIET -> AUDIO_ACTIVE` edge.
- Firmware and evidence contain no Wi-Fi password; the credential remains in
  ESP32 NVS and all console output is redacted.
