# SAFE-FIELD core MVP

This service keeps an occurrence session, ingests the FPGA bridge JSONL and
exposes a small local HTTP contract. It performs no recognition, biometrics,
institutional lookup or AI processing.

Start the server on the Raspberry:

```bash
python3 safe_field_core.py serve --host 0.0.0.0 --port 8765 \
  --sessions-root sessions --telemetry-jsonl ../live_telemetry.jsonl
```

Minimum occurrence API:

```text
POST /api/v1/occurrences/start
GET  /api/v1/status
POST /api/v1/occurrences/finish
POST /api/v1/capture_photo
GET  /api/v1/photos/<session_id>/<filename>
GET  /api/v1/wearable/state
```

`capture_photo` defaults to the UVC backend. When no physical camera exists it
returns `CAMERA_NOT_CONNECTED` and creates no JPEG. The mock backend is accepted
only when the server is started with both `--camera-backend mock` and
`--allow-mock`; its result is explicitly labeled `MOCK_PHOTO_CAPTURED`.

Wearable states are `SYSTEM_READY`, `OCCURRENCE_ACTIVE`, `AUDIO_QUIET`,
`AUDIO_ACTIVE`, `CAPTURE_PHOTO`, `PHOTO_CAPTURED`, `CAMERA_NOT_CONNECTED` and
`ATTENTION`. A future ESP32-S3 can poll `/api/v1/wearable/state`; ACTIVE audio
already maps to `AUDIO_ACTIVE` without changing the FPGA.

See `WEARABLE_CONTRACT.md` for the versioned state names and the first future
ESP32-S3 flow.
