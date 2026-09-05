# SAFE-FIELD operational extension

This additive service exposes the new occurrence-intelligence contract without
changing the frozen FPGA/TP4 bridge or the existing port-8765 service.

```powershell
$env:SAFE_FIELD_OPERATIONAL_API_TOKEN = '<provisioned-at-runtime>'
$env:SAFE_FIELD_OPERATIONAL_TLS_CERT = '/etc/safe-field/tls/fullchain.pem'
$env:SAFE_FIELD_OPERATIONAL_TLS_KEY = '/etc/safe-field/tls/privkey.pem'
python safe_field_operational_server.py --host 0.0.0.0 --port 8770 `
  --sessions-root sessions_operational `
  --diao-index ..\..\knowledge\diao\index `
  --ai-device cpu --asr-compute-type int8 `
  --pcm-port /dev/serial0
```

`0.0.0.0`, `::` and every other non-loopback bind fail closed unless both a
non-empty bearer token and native HTTPS are configured. The bearer comes from
`SAFE_FIELD_OPERATIONAL_API_TOKEN`; the certificate chain and private-key paths
come from `SAFE_FIELD_OPERATIONAL_TLS_CERT` and
`SAFE_FIELD_OPERATIONAL_TLS_KEY`. The equivalent `--tls-cert` and `--tls-key`
arguments override those path defaults, and the certificate/key must always be
provided as a pair. Use a certificate whose SAN covers the hostname or IP used
by the wearable, keep the private key readable only by the service account, and
never commit the bearer or private key.

Bearer values are never accepted on the command line or printed in logs. All
routes require `Authorization: Bearer <token>` whenever the bearer is set, and
JSON request bodies are limited to 64 KiB. Plain HTTP remains available only on
recognized loopback binds such as `127.0.0.1` for local software tests.
Readiness reports the selected `http://` or `https://` scheme.

The matching wearable credential must be provisioned separately through its
local setup channel and stored in ESP32 NVS. It must never be hardcoded in the
sketch, placed in a tracked `secrets.h`, or echoed over serial. Until the
wearable is provisioned to validate the HTTPS server and send the bearer header,
keep this service bound to `127.0.0.1` for software-only validation.

Routes:

```text
GET  /api/v1/operational/wearable/state
GET  /api/v1/operational/dashboard
GET  /dashboard
POST /api/v1/occurrences/start
POST /api/v1/hypotheses/confirm
POST /api/v1/hypotheses/reject
POST /api/v1/hypotheses/defer
POST /api/v1/guidance/action
POST /api/v1/occurrences/finish
```

The DIAO adapter is local and asynchronous. Guidance is withheld until an
officer confirmation and rejected if source metadata is incomplete. The local,
closed-world reasoning provider emits only transcript-grounded facts and
provisional hypotheses. Faster-Whisper and SpeechBrain ECAPA are used only when
their audited local model paths are configured. ECAPA embedding/re-ID passed its
controlled neural gate; multi-speaker diarization remains explicitly unavailable
because the attempted local VAD + clustering composition passed only 1/3
scenarios and was not enabled. Affected jobs persist as `PROCESSING_PENDING`
instead of receiving fabricated output.

## Optional Razer inference worker

Local inference remains the default. The launcher now has an additive remote
composition that reuses the same provider contracts while keeping capture,
speaker registry, occurrence files, confirmation, history and DIAO on the Pi.
It performs no network probe during startup and reports only
`CONFIGURED_NOT_PROBED`; a real worker failure becomes `ProviderUnavailable` and
the segment remains `PROCESSING_PENDING`.

Remote mode is selected explicitly by `--ai-mode razer` or
`SAFE_FIELD_AI_MODE=razer`. Values that contain secrets are accepted only via
environment variables:

```powershell
$env:SAFE_FIELD_AI_MODE = "razer"
$env:SAFE_FIELD_RAZER_WORKER_URL = "https://192.168.x.y:8766"
$env:SAFE_FIELD_RAZER_WORKER_TOKEN = Read-Host -MaskInput
$env:SAFE_FIELD_RAZER_SCOPE_SECRET = Read-Host -MaskInput
python safe_field_operational_server.py --host 127.0.0.1 --port 8770 `
  --sessions-root sessions_operational --diao-index ..\..\knowledge\diao\index
```

`SAFE_FIELD_RAZER_SCOPE_SECRET` is Pi-only and must differ from the worker
bearer. Neither value nor the worker URL is printed in readiness. The names of
the three environment variables can be changed with
`--razer-worker-url-env`, `--razer-worker-token-env` and
`--razer-scope-secret-env`. The remote timeout defaults to 90 seconds and is
configurable with `--razer-timeout-seconds`.

Non-loopback transport fails closed unless the URL is HTTPS and a bearer token
exists. Plain HTTP private-LAN testing requires the explicit
`--allow-insecure-razer-http` risk opt-in; it is not recommended because it
does not encrypt audio or credentials. Redirects and ambient HTTP proxies are
disabled by the transport.

The Razer worker itself defaults to CPU because CPU/int8 is the runtime that
passed the local model gates. GPU mode remains opt-in until the missing
`cublas64_12.dll` dependency is installed and the models are revalidated.

In both modes the launcher constructs
`MVPAsyncDIAOKnowledgeProvider(index_dir=--diao-index)` locally on the Pi. No
DIAO/PDF, guidance, occurrence dossier or final history is accepted by the
worker protocol.

`--pcm-port` is optional. Without it, the existing software-only behavior and
tests are unchanged. With it, WATCH `START` synchronously opens the additive
FPGA PCM stream at 1,500,000 baud and records mono signed PCM16 with a WAV rate
of 42,188 Hz (the exact FPGA rate is 42,187.5 Hz). A serial-open failure rejects
START and returns to `STANDBY`; it never leaves a phantom active occurrence.
WATCH `STOP` first stops the serial reader and only then closes `raw.wav`.

Live protocol counters are returned as `pcm_source` by the wearable-state API.
Final counters are also preserved in each session as
`audio/pcm_transport.json`: CRC errors, format errors, discarded bytes,
sequence/sample losses, I2S frame-error flags, transport-overrun flags and
read/sink errors. The UART PCM build is additive and does not alter the frozen
TP4 telemetry bridge.
