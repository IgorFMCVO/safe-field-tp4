# SAFE-FIELD MVP — validação física do transporte PCM

Data: 2026-09-05 (America/Sao_Paulo).

## Resultado

`PHYSICAL_PCM_TRANSPORT = PASS`

A variante separada foi programada somente em SRAM. A Flash e o TP4 congelado
não foram alterados. A câmera permaneceu fora do escopo e nenhuma conexão
física foi modificada.

| Verificação | Valor | Resultado |
|---|---:|---:|
| Dispositivo JTAG | GW1NSR-4C, ID `0x0100981B` | PASS |
| Operação | 2, SRAM Program | PASS, 100% |
| User/Status Code | `0x000023A5` / `0x0003F020` | PASS |
| UART Raspberry | `/dev/serial0` → `/dev/ttyS0`, 1.500.000 baud | PASS |
| Janela real | 10,021174 s | PASS |
| Frames protocolados válidos | 13.180 | PASS |
| Samples PCM16 LEFT | 421.760 (9,997274 s pela taxa física) | PASS |
| CRC errors | 0 | PASS |
| Format errors / bytes descartados | 0 / 0 | PASS |
| Sequence losses | 0 | PASS |
| Sample losses | 0 | PASS |
| I2S frame-error packets | 0 | PASS |
| Transport-overrun packets | 0 | PASS |
| Exit code do collector | 0 | PASS |

## Estabilidade contínua de 60 segundos (evidência legada pré-endurecimento)

| Verificação | Valor | Resultado |
|---|---:|---:|
| Janela real | 60,010715 s | PASS |
| Duração pelos samples | 59,985920 s | PASS |
| Frames protocolados válidos | 79.083 | PASS |
| Samples PCM16 LEFT | 2.530.656 | PASS |
| CRC / formato | 0 / 0 | PASS |
| Alinhamento antes do primeiro sync | 40 bytes | registrado |
| Ressincronização após primeiro frame | 0 bytes | PASS |
| Sequence / sample losses | 0 / 0 | PASS |
| Frame-error / overrun packets | 0 / 0 | PASS |

O WAV local ignorado tem SHA-256
`73741D23BE0B1BFFC44BF47AE54149809D3C590C64EC60E3B09A1177A7DBBF8E`.
Foram observados 2.495.377 samples não-zero, 215 valores distintos, mínimo
-126, máximo 88 e RMS 30,6936. A captura mede estabilidade do transporte e não
é apresentada como fala física.

## Lifecycle sobre UART física, acionado por utilitário

O utilitário `physical_watch_capture.py` executou o mesmo contrato de serviço
usado pelo wearable contra `/dev/serial0`. Não houve toque nem firmware wearable
operacional neste gate:

| Verificação | Valor | Resultado |
|---|---:|---:|
| START abriu UART exclusiva | 1.500.000 baud | PASS |
| Frames / samples no Core | 13.180 / 421.760 | PASS |
| Frames em `audio/raw.wav` | 421.760 @ 42.188 Hz | PASS |
| Alinhamento antes do primeiro sync | 0 bytes | PASS |
| CRC, formato e resync | 0 / 0 / 0 | PASS |
| Sequence/sample loss | 0 / 0 | PASS |
| Frame error/overrun | 0 / 0 | PASS |
| Read/sink errors | 0 / 0 | PASS |
| STOP drenado / histórico lifecycle-only | sim / gerado | PASS |
| Segmentos / jobs concluídos | 0 / 0 | registrado |

Pacote local ignorado:
`mvp/evidence/physical_watch_pcm/physical_watch_pcm_002_evidence.tar.gz`.
SHA-256:
`C643D7C692620CFDA2C1D6A02695B43E83D6940DD1C8B1F6B57BE804EE88B869`.

Resultado: `PHYSICAL_PCM_LIFECYCLE_CONTRACT = PASS`.

O Markdown/JSON final é estruturalmente válido, porém semanticamente vazio
(sem transcript, speaker, fato, hipótese ou guidance), como esperado para esta
janela sem fala controlada. Ele não é evidência de pipeline de inteligência nem
de interação física com o relógio.

## Revalidação fail-closed — código final

Os contadores foram posteriormente separados em alinhamento anterior ao
primeiro frame, ressincronização posterior e descontinuidades de sequência e de
contador absoluto. Captura vazia, duração inválida e divergência entre pacotes,
samples recebidos e frames no WAV também passaram a falhar explicitamente.

Com esses checks já instalados na Raspberry, sem reprogramar a FPGA:

| Verificação | WATCH PCM 003 | Estabilidade 60 s v2 |
|---|---:|---:|
| Wall time | 10 s solicitado | 60,010637 s |
| Frames válidos | 13.180 | 79.084 |
| Samples | 421.760 | 2.530.688 |
| Razão observado/esperado | 0,999727 | 0,999778 |
| Startup alignment | 43 bytes | 0 bytes |
| Startup candidate errors | 0 | 0 |
| Resync pós-lock | 0 | 0 |
| CRC / formato | 0 / 0 | 0 / 0 |
| Perdas seq/sample | 0 / 0 | 0 / 0 |
| Descontinuidades seq/sample | 0 / 0 | 0 / 0 |
| I2S frame error / overrun | 0 / 0 | 0 / 0 |
| Read / sink errors | 0 / 0 | n/a no collector síncrono |
| Invariantes | PASS | PASS |
| Acceptance | PASS | PASS |

O `raw.wav` do WATCH PCM 003 tem SHA-256
`728F11A9BE2BF0B8FA778BDAB6849AEC77231DA1BB199AFC68A67762EBCF3F1F`,
416.729 samples não-zero, 427 valores distintos, mínimo -198, máximo 231 e
RMS 42,2250. Seu pacote local ignorado tem SHA-256
`655B7988C53A0D2AF35B3C558762E6829FACCD587497413E7BC13EAB72F873D1`.

O WAV de 60 s v2 tem SHA-256
`F52CC060B6E9D4BF7406AD21D7999F865C5D61B56124FE80A5AFAE46B5D2BFE3`,
2.512.837 samples não-zero, 588 valores distintos, mínimo -236, máximo 355 e
RMS 49,4487. Seu pacote local ignorado tem SHA-256
`E1808B6C0BE24A16F804E1BCD04BB679C7509832B8B53260FA938EFC27819A90`.

Essas repetições substituem a lacuna probatória das capturas anteriores, cujos
sidecars ainda não separavam `startup_alignment` de `resync`.

## Artefatos

- Machine-readable counters/statistics (tracked, no audio):
  `PHYSICAL_WATCH_PCM_003.json`, `PHYSICAL_WATCH_PCM_003.analysis.json`,
  `PHYSICAL_STABILITY_60S_V2.json` and
  `PHYSICAL_STABILITY_60S_V2.analysis.json`;
- provenance/hash manifest for those copies:
  `PHYSICAL_MACHINE_EVIDENCE_MANIFEST.md`;
- Bitstream:
  `build/mvp_pcm_stream/impl/pnr/safe_field_mvp_pcm_stream.fs`;
- SHA-256 do bitstream:
  `F46314D4A3478B6157A5253DF07E2AAB2022D305EA16E94E0F9F9A8706C0EC7B`;
- scan JTAG: `01_jtag_scan.log`;
- transcript de programação: `02_sram_program.log`;
- leitura pós-programação: `03_read_device_codes.log`;
- WAV e sidecars: `mvp/evidence/physical_pcm_transport/` (locais e ignorados
  pelo Git, para não publicar áudio de ocorrência).

SHA-256 do WAV real de 10 s:
`7B78000799AFA390B1C8A2340EF6F73F4A1BAB05A04E0276FE4E7CD6B26D38AB`.

Métricas do sinal durante a janela sem estímulo controlado: mínimo -113,
máximo 84, média absoluta 21,6317, RMS 29,4138, pico 113, 416.279 samples
não-zero e 196 valores distintos. Faster-Whisper retornou transcript vazio,
coerente com a ausência de uma fala controlada; isto não é evidência de ASR
físico PASS nem FAIL.

## Tentativa acústica autônoma

Sem solicitar fala ao operador, o Razer executou playback síncrono do fixture
TTS pt-BR `A_conflict_four_speakers/segment_002.wav` durante uma segunda
captura física de 16,036 s. O transporte permaneceu íntegro: 21.109 frames,
675.488 samples, CRC/formato/perdas/frame errors/overruns em zero. Houve 44
bytes iniciais descartados até o primeiro sync, sem perda posterior.

O RMS medido foi 30,5019 contra 29,4138 no silêncio (razão 1,037) e o ASR
retornou vazio. Portanto o playback não produziu estímulo acústico comprovável
no INMP441 e **não** é aceito como teste físico de ASR. Isto não invalida o
stream PCM nem é usado para diagnosticar falha do microfone. O WAV local
ignorado tem SHA-256
`FCEBBA72D36A36357B90B297374CFE0DFAC698E15BA035433A9E9717C52B4159`.

## Comandos executados

```powershell
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\Programmer\bin\programmer_cli.exe' `
  --device GW1NSR-4C --operation_index 2 --frequency 2.5MHz `
  --fsFile 'C:\SAFE-FIELD\fpga\tp4-audio-inmp441\build\mvp_pcm_stream\impl\pnr\safe_field_mvp_pcm_stream.fs' `
  --cable-index 1
```

```bash
python3 safe_field_pcm_receiver.py --port /dev/serial0 --duration 10 \
  --output /home/safe-field/safe-field-mvp-pcm/physical_gate_10s.wav
```

```bash
python3 raspberry_mvp/pcm_stream/physical_watch_capture.py \
  --port /dev/serial0 --duration 10 \
  --sessions-root /home/safe-field/safe-field-mvp-watch-gate-20260905/sessions \
  --occurrence-id PHYSICAL_WATCH_PCM_002 \
  --output /home/safe-field/safe-field-mvp-watch-gate-20260905/physical_watch_pcm_002.json
```

O bridge TP4 de 115.200 baud foi interrompido antes do gate para não disputar a
UART nem interpretar o stream PCM. Ele não foi reiniciado enquanto a variante
PCM de 1,5 Mbaud permaneceu em SRAM.
