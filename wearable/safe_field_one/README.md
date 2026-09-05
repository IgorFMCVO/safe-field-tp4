# SAFE-FIELD One wearable firmware

Minimal firmware for the Waveshare ESP32-S3-Touch-AMOLED-2.06. It uses the
official CO5300 display driver and polls the existing SAFE-FIELD Core endpoint:

`GET /api/v1/wearable/state`

The firmware renders a dark, high-legibility operational view. It maps the
versioned Core states without adding another backend. A 140 ms motor pulse on
GPIO18 occurs only on `AUDIO_QUIET -> AUDIO_ACTIVE`; GPIO18 is the `MOTOR` net
in the official V1.0 schematic.

## Credentials

No Wi-Fi SSID, password, or Core address is compiled into the binary. Provision
over the native USB serial port; values are stored in ESP32 NVS:

```powershell
$env:SAFE_FIELD_WIFI_SSID = "..."
$env:SAFE_FIELD_WIFI_PASSWORD = "..."
$env:SAFE_FIELD_CORE_URL = "http://<raspberry-ip>:8765/api/v1/wearable/state"
.\PROVISION.ps1 -Port COM7
```

The script redacts the password from output. `SHOW_CONFIG` never reveals it.

## Build

`BUILD.ps1` uses Arduino-ESP32 3.3.11 and the exact FQBN/options used by the
Waveshare first-party CI. The bundled first-party Arduino libraries are taken
from the audited Waveshare checkout outside this repository.

```powershell
.\BUILD.ps1
```

Upload is deliberately explicit and only follows a successful compile:

```powershell
.\BUILD.ps1 -Upload -Port COM7
```
