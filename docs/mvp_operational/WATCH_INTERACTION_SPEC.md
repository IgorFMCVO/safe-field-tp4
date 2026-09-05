# SAFE-FIELD operational wearable interaction specification

## States and intent

`STANDBY` means no occurrence is recording. `OCCURRENCE_ACTIVE` means continuous
capture is running regardless of silence or FPGA QUIET/ACTIVE classification.
The wearable never uses VAD as a recording gate.

## Primary actions

| Wearable action | API operation | Core effect |
|---|---|---|
| `INICIAR OCORRÊNCIA` | `POST /api/v1/occurrences/start` | Create occurrence and start continuous capture |
| `CONFIRMAR` | `POST /api/v1/hypotheses/confirm` | Mark a proposed hypothesis `OFFICER_CONFIRMED` and permit DIAO guidance display |
| `DESCARTAR` | `POST /api/v1/hypotheses/reject` | Mark hypothesis `OFFICER_REJECTED` |
| `MAIS DADOS` | `POST /api/v1/hypotheses/defer` | Keep capture active without confirmation |
| `REALIZADO/PENDENTE/NÃO APLICÁVEL` | `POST /api/v1/guidance/action` | Append a sourced action status to the timeline |
| `FINALIZAR OCORRÊNCIA` | `POST /api/v1/occurrences/finish` | Stop capture, drain jobs and build preliminary history |

The regression fixture `WEARABLE_SIMULATION` calls the same routes for
`START -> CONFIRM -> ACTION_DONE -> STOP`; no human touch is required.

STOP uses a short processing wait and accepts the Core's retryable HTTP 200
response even when it carries `ok:false` with `STOPPING`/`PROCESSING_PENDING`.
In that state `capture_active:false` is authoritative: the screen displays
`FINALIZANDO` and `CAPTURA ENCERRADA`, never `CAPTURA CONTÍNUA`. A later touch
may retry finalization without closing or duplicating the recording. The
production binary disables the serial `APPLY_JSON` fixture hook; it is available
only in an explicitly test-enabled build.

A transport-integrity failure is deliberately different from processing wait.
The finish response and subsequent wearable-state polls carry these exact
machine-readable fields:

```json
{
  "ok": false,
  "state": "CAPTURE_FAILED",
  "lifecycle_state": "STOPPING",
  "capture_active": false,
  "source_quiescent": true,
  "finalization_pending": false,
  "finalization_blocked": true,
  "retryable": false,
  "reason": "PCM_TRANSPORT_FAILED",
  "pcm_failure_fields": ["crc_errors"]
}
```

The UI must recognize `state=CAPTURE_FAILED` before its generic
`PROCESSING_PENDING` rule and render a non-retryable capture-integrity warning
(for example, `CAPTURA INVÁLIDA / DADOS PRESERVADOS`). It must not offer
`TENTAR FINALIZAR` as if queue drainage could repair lost or corrupt PCM. The
Core intentionally retains the occurrence and evidence while its internal
lifecycle remains `STOPPING`; no `FINISHED` status or preliminary history is
published.

The same state can arrive while the Core lifecycle is still `ACTIVE` if the
serial reader or its PCM sink fails before the officer requests STOP. In that
case `source_quiescent` is authoritative for the capture flag:

- `CAPTURE_FAILED + source_quiescent=false` keeps `capture_active=true` only
  while an in-flight reader delivery may still exist. In that state the UI
  exposes `FINALIZAR CAPTURA`, and touch or serial STOP may close the source;
- `CAPTURE_FAILED + source_quiescent=true` requires `capture_active=false`;
  the UI removes the finalization action and rejects repeated serial STOP;
- neither response auto-finishes the occurrence or publishes history; the
  officer's later STOP persists/closes the evidence once and becomes
  `FINALIZATION_BLOCKED`.

The firmware contract suite passed 25/25 tests and the production build compiled
without upload. Binary SHA-256:
`0FEEC4A60FA9C9F4AB66A4ADE82BE22D35818589C931F1DA07C1B50829A41C6A`.

## Transport security

The production firmware sends its bearer only over `https://`. A CA PEM is
provisioned separately into ESP32 NVS, passed to `WiFiClientSecure::setCACert`
and never compiled into the image. Plain HTTP, an absent/invalid CA, URL
credentials, arbitrary base paths and redirects all fail closed before the
Authorization header can be transmitted; `setInsecure()` is forbidden. The
Core hostname or IP must match the certificate SAN. Firmware compilation proves
the transport implementation, but the operational watch remains undeployed
until the Core TLS certificate and matching CA trust are provisioned.

## Guidance safety contract

Operational guidance is hidden while a hypothesis is merely `PROPOSED`.
After officer confirmation, the Core may display at most five concise priority
actions. Every action retains `source_document`, `source_version`, `section`,
physical/printed page, item and `chunk_id`. If no sufficiently relevant source
exists, the wearable displays `ORIENTAÇÃO INDISPONÍVEL`, never an invented
fallback.

New contradictory information produces `REASSESSMENT_REQUIRED`; it cannot
silently replace a confirmed hypothesis. A newly confirmed hypothesis triggers
a new DIAO retrieval.
