# SAFE-FIELD autonomous wearable audio self-test

Branch-only diagnostic firmware for the Waveshare ESP32-S3 Touch AMOLED 2.06.
It preserves Wi-Fi/Core polling and adds a local HTTP audio playback endpoint:

`POST /api/v1/selftest/play?profile=speech&volume=70`

The response is immediate; progress is available at `GET /api/v1/selftest/status`.
Each run emits two seconds of digital silence, a 4.425 s offline pt-BR SAPI
phrase, then two seconds of silence. The source WAV is mono PCM16/16 kHz and
is embedded as dual mono because the first-party I2S example uses both slots.

No Wi-Fi password or Core URL is compiled into the image. Existing NVS values
from `safe_field_one` are reused. Upload affects only the ESP32 wearable; the
Tang build is programmed separately and only into SRAM.
