# SAFE-FIELD operational wearable v1

Firmware variant for the Waveshare ESP32-S3 Touch AMOLED 2.06. It preserves
all previous wearable firmware and implements the operational, occurrence-led
interaction only. Camera flows are deliberately absent.

## Safety and state semantics

- `STANDBY` means no occurrence and no global recording.
- `INICIAR OCORRÊNCIA` starts an occurrence through the Core.
- `OCCURRENCE_ACTIVE` means capture remains continuous until the explicit
  `FINALIZAR OCORRÊNCIA` action.
- FPGA `AUDIO_QUIET` and `AUDIO_ACTIVE` are accepted as telemetry compatibility
  states, but never start, stop or gate recording.
- A `PROPOSED` hypothesis exposes only `CONFIRMAR`, `DESCARTAR` and `MAIS DADOS`.
- Guidance is rendered only when the corresponding hypothesis is
  `OFFICER_CONFIRMED`. It shows three to five sourced priority actions.
- Each guidance item can be marked `REALIZADO`, `PENDENTE` or `NÃO APLICÁVEL`.
- `REASSESSMENT_REQUIRED` is a visible alert; the firmware does not silently
  replace a confirmed hypothesis.
- During `STOPPING`, the Core state is normalized to `PROCESSING_PENDING` with
  `capture_active=false`; the screen says `FINALIZANDO / CAPTURA ENCERRADA`.
  A `PROCESSING_PENDING` response with `capture_active=true` instead means the
  occurrence capture is still running.
- `CAPTURE_FAILED` with `retryable=false` is an explicit integrity-failure
  screen. It never becomes `STANDBY` or `FINALIZANDO` and always states that no
  history was generated. If the Core reports `capture_active=true` and
  `source_quiescent=false`, the screen exposes only `FINALIZAR CAPTURA` so the
  operator can stop the still-unwinding source. Once `capture_active=false` or
  `source_quiescent=true`, that action disappears and repeated STOP is blocked.

## HTTP contract

The configured value in NVS may be either the Core base URL or an older full
endpoint. The firmware derives the origin and uses these exact v1 routes:

```text
GET  /api/v1/operational/wearable/state
POST /api/v1/occurrences/start
POST /api/v1/hypotheses/confirm
POST /api/v1/hypotheses/reject
POST /api/v1/hypotheses/defer
POST /api/v1/guidance/action
POST /api/v1/occurrences/finish
```

`FINALIZAR OCORRÊNCIA` asks the Core to drain for 1.0 second and allows up to
3.5 seconds for the HTTP exchange. A 2xx response with `ok:false` plus
`STOPPING`, `finalization_pending` or `retryable` is a valid pending result,
not discarded as a transport error; the operator may retry finalization.

Every GET and POST includes `Authorization: Bearer <token>` only inside a TLS
connection validated against a provisioned CA certificate. Wi-Fi, Core URL,
bearer token and CA are never compiled into the firmware; they are stored in
the ESP32 NVS namespace `safe-field`. Plain HTTP is rejected, redirects are
disabled, `setInsecure()` is not used, and the bearer is not attached unless
the URL is an `https://` origin and a syntactically valid CA PEM is present.
Certificate-chain and hostname verification are therefore performed by
`WiFiClientSecure` before HTTP authentication data is sent.

The client fails closed when the token or CA is absent and treats HTTP 401 as
`AUTH NECESSÁRIA`, without printing the token, CA contents or response body.
An older `http://` value already stored in NVS is not migrated or contacted;
the screen reports `TLS NECESSÁRIO` until it is replaced.

Provision the same runtime token configured in the Core's
`SAFE_FIELD_OPERATIONAL_API_TOKEN` through native USB serial:

```text
SET_CORE https://<raspberry-hostname-covered-by-certificate>:8770
SET_CA_PEM -----BEGIN CERTIFICATE-----\n<base64-lines-with-\n>\n-----END CERTIFICATE-----\n
SET_TOKEN <bearer-token>
SHOW_CONFIG
```

`SET_CA_PEM` takes one serial line, with each PEM newline encoded as the two
characters `\n`; certificates larger than 3900 bytes are rejected to respect
the ESP32 NVS string bound. `SHOW_CONFIG` reports only `token=SET_REDACTED` and
`ca=SET_REDACTED` (or `NOT_SET`), plus `tls=READY|BLOCKED`. Use `CLEAR_TOKEN`
and `CLEAR_CA` to remove the stored values. Do not put the token in a
versioned script, command transcript or screenshot. The CA certificate is
public material but remains runtime configuration so deployment trust can be
rotated independently from firmware.

The Core endpoint must provide TLS directly or sit behind a local reverse
proxy whose certificate chains to the provisioned CA and whose SAN covers the
exact hostname/IP in `SET_CORE`. Do not work around a name mismatch with an
insecure client mode.

Action status labels map to stable JSON values: `REALIZADO -> DONE`,
`PENDENTE -> PENDING`, and `NÃO APLICÁVEL -> NOT_APPLICABLE`.

The state response accepts this minimal schema:

```json
{
  "ok": true,
  "version": "1.0",
  "state": "HYPOTHESIS_PROPOSED",
  "occurrence_id": "OCC_001",
  "capture_active": true,
  "hypothesis": {
    "hypothesis_id": "HYP_001",
    "label": "POSSIVEL ...",
    "status": "PROPOSED",
    "confidence": 0.74
  },
  "guidance": {
    "status": "SUPPORTED",
    "items": []
  }
}
```

Every guidance item may include `action_id`, `text`, `status`, `section`,
`page`, `item` and `chunk_id`. Source metadata is retained by the Core; the
wearable displays concise action text only.

## Touch and serial fallback

Touch uses the official FT3168 wiring (`SDA=15`, `SCL=14`, `INT=38`). Buttons
are state-dependent. Equivalent USB serial commands support repeatable tests:

```text
START
CONFIRM
REJECT
MORE_DATA
ACTION <1-5> DONE|PENDING|NOT_APPLICABLE
STOP
POLL
SHOW_CONFIG
SET_CORE https://<core-host>:<port>
SET_CA_PEM <single-line escaped CA PEM>
CLEAR_CA
SET_TOKEN <bearer-token>
CLEAR_TOKEN
SET_WIFI <ssid><TAB><password>
```

Credentials remain in the existing `safe-field` NVS namespace and are never
compiled or printed. The `APPLY_JSON` simulation hook is disabled in the
normal build. It exists only behind `SAFE_FIELD_ENABLE_TEST_HOOKS=1` and can be
compiled explicitly for a lab-only regression artifact:

```powershell
.\BUILD.ps1 -EnableTestHooks
```

Never deploy a test-hook-enabled artifact operationally.

## Test and build

```powershell
python .\tests\test_contract.py
.\BUILD.ps1
```

`BUILD.ps1` compiles without uploading unless the operator explicitly supplies
`-Upload`. This sprint intentionally performs compile-only validation.
