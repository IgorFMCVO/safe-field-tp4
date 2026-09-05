# SAFE-FIELD operational intelligence core

This package is an additive MVP component. It does not modify the frozen TP4,
FPGA logic, UART bridge or wearable firmware.

The lifecycle is explicit:

1. `OperationalIntelligenceCore.start()` creates one occurrence directory.
2. `ingest_pcm()` writes every input frame to `audio/raw.wav`, regardless of
   silence or FPGA QUIET/ACTIVE state.
3. Silence only closes a WAV segment. Closed segments enter a durable,
   non-blocking background processing queue.
4. `confirm_hypothesis()` records a watch/officer decision. Knowledge retrieval
   occurs only after `CONFIRM` and guidance without source records is rejected.
5. `stop()` first quiesces the PCM source, then closes the final segment once.
   A final transport snapshot with any integrity error keeps the lifecycle in
   `STOPPING/FINALIZATION_BLOCKED`, exposes `CAPTURE_FAILED` plus
   `retryable=false` to the watch API, returns `PCM_TRANSPORT_FAILED`, and emits
   no history. Repeating STOP is idempotent but cannot erase a capture error.
6. With an error-free transport, STOP drains jobs. A timeout keeps the lifecycle
   in `STOPPING/FINALIZATION_PENDING`; calling `stop()` again safely resumes
   finalization. Both history formats are emitted only after transport and queue
   gates pass with zero failures.

Live source health is also fail-closed. A threaded PCM source exposes
`reader_alive` and `quiescent`; an asynchronous read/sink failure is immediately
reported as `CAPTURE_FAILED`. The watch's `capture_active` flag becomes false
only after the reader is quiescent. The Core retains the active occurrence and
open evidence until an explicit STOP; it never auto-finishes or publishes a
history in response to a transport thread failure.

Default providers intentionally report `PROCESSING_PENDING`. A deployment must
inject configured local implementations through `PipelineProviders`; missing
providers never cause captured audio to be discarded.
ASR output is written before diarization/embedding, so a downstream provider
failure preserves the raw transcript as well as its source WAV and pending job.

`http_api.py` adds the versioned watch contract and a local engineering
dashboard. The additive launcher is
`raspberry/safe_field_core/safe_field_operational_server.py`; it mounts the real
local DIAO adapter and does not change the approved port-8765 Core.

The frozen Tang→Pi protocol carries only energy/state telemetry. A separately
built PCM variant under `verilog_mvp/pcm_stream` passed its physical SRAM
transport gate with zero protocol loss/error. The optional `PCMSource` boundary
now connects that receiver to WATCH lifecycle without changing the no-source
path: START opens the source transactionally, STOP quiesces it before closing
the recorder, and transport counters are exposed and persisted. See
`raspberry/safe_field_core/OPERATIONAL_EXTENSION.md` for deployment arguments.
