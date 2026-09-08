# WATCH MICROPHONE CONTROL REPORT

Data: 2026-09-07/08 (America/Sao_Paulo).

## Resultado

`WATCH_MIC_ES7210_CAPTURE = PASS`

O teste utilizou os microfones do Waveshare ESP32-S3 Touch AMOLED 2.06 como
controle independente. O caminho correto é ES7210; o ES8311 fica reservado ao
codec de reprodução. A tentativa anterior que leu zeros pelo ES8311 foi
invalidada e não entrou na conclusão.

## Captura válida

- Duração: 8,0 s
- Sample rate: 16.000 Hz
- Frames: 128.000 estéreo
- Canal escolhido: 0
- RMS AC: 329,005
- Pico absoluto: 2.974
- Valores distintos: 3.495
- Clipping: 0
- ASR: `Teste Safety Field, teste de áudio, teste de gravação de áudio do Safety Field.`
- Confiança ASR: 0,7656
- SHA-256 WAV mono: `617D16574E97086F55600F3C4AE6F5BD928B443A8A4288E9082985B832EB0C70`

## Interpretação

Voz humana normal foi convertida em PCM útil e transcrita pelo mesmo ambiente
de análise. Isso valida o controle independente e reforça que a ausência de
fala no caminho Tang/INMP441 não é causada pelo ASR nem por uma incapacidade
geral do host de processar voz. O principal suspeito permanece o módulo INMP441
ou seu caminho acústico interno.

## Arquivos

- `capture_voice_es7210_01/watch_mic_stereo.wav`
- `capture_voice_es7210_01/watch_mic_mono.wav`
- `capture_voice_es7210_01/watch_mic_capture.json`
- `capture_voice_es7210_01/analysis`
- `capture_voice_es7210_01/asr.log`
- `compile_es7210.log`
- `upload_es7210.log`
