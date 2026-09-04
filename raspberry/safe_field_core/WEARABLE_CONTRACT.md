# SAFE-FIELD wearable contract v1

This is the local contract for a future ESP32-S3 client. It is transport-light
and contains no biometric or AI semantics.

## Endpoint

`GET /api/v1/wearable/state`

The current implementation uses local HTTP. A future WebSocket transport may
carry the same state names and payload fields without changing their meaning.

## States

- `SYSTEM_READY`
- `OCCURRENCE_ACTIVE`
- `AUDIO_QUIET`
- `AUDIO_ACTIVE`
- `CAPTURE_PHOTO`
- `PHOTO_CAPTURED`
- `CAMERA_NOT_CONNECTED`
- `ATTENTION`

## First target flow

`FPGA ACTIVE -> Raspberry event -> AUDIO_ACTIVE -> future watch notification`

The FPGA remains the deterministic source of the audio activity decision. The
Raspberry only validates, records and publishes that event.

## Camera flow

`CAPTURE_PHOTO` requests the configured camera backend. A successful physical
UVC capture becomes `PHOTO_CAPTURED`; absence of a real UVC camera becomes
`CAMERA_NOT_CONNECTED`. Mock results are explicitly labeled and are never
presented as physical evidence.
