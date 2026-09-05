# Physical PCM machine-readable evidence manifest

The four JSON files in this directory are content-equivalent copies of the
machine-readable outputs preserved with the private local WAV packages. They
contain counters/statistics only; no audio, transcript, credential or DIAO
content is committed. Text line endings may be normalized by `.gitattributes`.

| Tracked evidence | Original private artifact SHA-256 | Semantic JSON comparison |
|---|---|---:|
| `PHYSICAL_WATCH_PCM_003.json` | `D04FB943A4CD26597D91118DBD0CE57B6BFD6D81DA2F14267E3102CF83C867D3` | EQUAL |
| `PHYSICAL_WATCH_PCM_003.analysis.json` | `B44EDD314CD812B3EE53EFB18B0207B4AF695DE12C0D591D7CC92AAF900EC62C` | EQUAL |
| `PHYSICAL_STABILITY_60S_V2.json` | `12A7F41E2002305D5B610F27C7D553DA8139EA7F0AC775BD490B035EA2F31119` | EQUAL |
| `PHYSICAL_STABILITY_60S_V2.analysis.json` | `727F3A7D071F5FB1C83C7A84A41C27D5E7F66D83EFC19124950DACD21D363C00` | EQUAL |

Private package SHA-256 values, retained locally and not committed:

- WATCH PCM 003 package:
  `655B7988C53A0D2AF35B3C558762E6829FACCD587497413E7BC13EAB72F873D1`;
- 60-second v2 package:
  `E1808B6C0BE24A16F804E1BCD04BB679C7509832B8B53260FA938EFC27819A90`.

The corresponding WAV hashes are present in the `.analysis.json` files. The
WAV bytes remain private and ignored; the committed evidence therefore permits
auditing every asserted counter and signal statistic without publishing audio.
