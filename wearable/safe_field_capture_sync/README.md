# SAFE-FIELD capture synchronization diagnostic

Additive wearable diagnostic used to synchronize three physical RAW24 voice
windows with the Tang LED. It is based on `safe_field_one` but shows explicit
`CAPTURANDO / CAPTURA` while the Raspberry publishes `AUDIO_ACTIVE`, and
`QUIET` while it publishes `AUDIO_QUIET`.

The diagnostic does not change the frozen TP4, FPGA RTL, I2S path or audio
thresholds. Restore `safe_field_operational_v1` after the measurement campaign.
