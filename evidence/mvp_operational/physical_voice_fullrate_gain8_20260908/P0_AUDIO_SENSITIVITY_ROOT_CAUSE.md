# P0 AUDIO SENSITIVITY ROOT CAUSE

Data: 2026-09-07/08 (America/Sao_Paulo). Branch:
`mvp-occurrence-recovery-ptbr-physical`.

O TP4 congelado não foi alterado. Os instrumentos e bitstreams deste relatório
são aditivos e foram programados exclusivamente em SRAM.

## Resultado executivo

Classificação: **E — MICROPHONE SUSPECT** (transdutor/caminho acústico interno
do módulo), depois de excluir as hipóteses de software A/B/C.

A janela de voz foi sincronizada por dois pulsos de LED, seguida por LED aceso
durante 10 s. O transporte foi íntegro: 455.360 samples, 10,7937 s, 14.230
pacotes, CRC=0, perdas=0, frame errors I2S=0 e overruns=0.

Mesmo assim, a banda 300–3400 Hz da janela de voz mediu 19,22 RMS contra 19,52
RMS no silêncio (`0,985x`, `-0,13 dB`). Não há bursts, formantes nem envelope
de fala. Portanto não existe conteúdo acústico mensurável para o ASR.

## Gates matemáticos e de transporte

| Gate | Resultado | Evidência |
|---|---|---|
| I2S FORMAT | PASS | 24-bit signed, MSB first, 1-bit delay, 32 SCK/slot, 64 SCK/frame |
| I2S ALIGNMENT | PASS | bits 1..24 capturados; TB e frame errors=0 |
| SAMPLE24 TEST | PASS | testes determinísticos anteriores cobrem sinal, limites e níveis |
| PCM16 CONVERSION | PASS | `PCM16 = saturate(sample24 >>> 5)` no gain8; sem double shift |
| UART AMPLITUDE | PASS | TB de payload/CRC e transporte físico sem perdas |
| WAV AMPLITUDE | PASS | PCM16 little-endian preservado; ganho observado ~8x contra `>>>8` |
| SNR CALCULATOR | PASS | voz e silêncio comparados no mesmo domínio, escala e banda; DC removido |

## Medições da captura sincronizada

| Medida | Voz LEFT gain8 | Silêncio LEFT gain8 |
|---|---:|---:|
| min / max PCM16 | -635 / 638 | -966 / 651 |
| DC | -8,082 | -103,556 |
| AC RMS global | 154,312 | 245,744 |
| pico | 638 | 966 |
| clipping | 0 | 0 |
| RMS 300–3400 Hz | 19,22 | 19,52 |
| RMS 80–7600 Hz | 28,51 | 28,81 |

Equivalente aproximado no domínio sample24 (sem saturação, reversão do shift
`>>>5`): silêncio AC RMS ≈ 7.864; sinal AC RMS ≈ 4.938; sinal/silêncio global
≈ `0,628x`. Na banda de voz, sinal/silêncio = `0,985x`.

O ASR large-v3-turbo retornou `Obrigado.` com confiança 0,52. A saída foi
**REJEITADA**: não há energia/envelope de fala que a suporte e ela é consistente
com alucinação do ASR sobre ruído.

## Prova do canal

Foi criado `mvp_pcm_stream_gain8_right`, que muda apenas a observação UART do
slot WS=0 para WS=1. Simulação: PASS. Síntese/P&R/STA: PASS, setup violations=0,
hold violations=0. O pinout permaneceu 40/41/42/43/45/10/39/46.

Captura física RIGHT: 126.016/126.016 samples exatamente zero, CRC=0,
perdas=0 e frame errors=0. Assim, o INMP441 dirige o slot LEFT como esperado e
o slot RIGHT permanece em alta impedância/pull-down. Canal invertido foi
excluído.

Bitstream RIGHT diagnóstico:
`C:\SAFE-FIELD\fpga\tp4-audio-inmp441\build\mvp_pcm_stream_gain8_right\impl\pnr\safe_field_mvp_pcm_stream_gain8_right.fs`

SHA-256: `449582CE6662547C899D15CA16728C3C46B5910684E6D0D7B8C1DBB7F2BE2649`.

Warnings de P&R: 7 no total — 6 `PA1001` de nets somadores sem destino no
receptor e 1 `PR1014` já conhecido sobre roteamento genérico de `sys_clk_d`.
Nenhum foi ocultado; não explica ausência de áudio.

Ao final, a SRAM foi restaurada ao build LEFT gain8, hash
`9941D50499C18C943BA9E4EEE6857677EB51084D0B91C2D08A816FEC7C93D70E`.
GPIO17 ficou LOW e o wearable em `AUDIO_QUIET`.

## Perda de amplitude

| Trecho | Ganho/perda observada |
|---|---|
| I2S sample24 → PCM16 | transformação esperada `>>>5`, sem perda adicional; ganho8 preserva 3 bits a mais que `>>>8` |
| PCM16 → UART | 1,0x, exato nos testes; CRC/perdas físicos iguais a zero |
| UART → WAV | 1,0x, amostras PCM16 gravadas sem normalização |

O ganho8 ampliou o conteúdo anterior em aproximadamente 8x, inclusive o piso
de ruído, mas não revelou voz. Isso prova que a energia de voz já está ausente
antes da conversão PCM16/UART/WAV.

## Ação física mínima

## Controle independente pelo microfone do wearable

Em 2026-09-07/08 foi executada uma captura independente com os dois microfones
do Waveshare ESP32-S3 Touch AMOLED 2.06. A primeira tentativa retornou zeros
porque o firmware diagnóstico acionava o ADC do ES8311; ela foi rejeitada. O
BSP oficial confirma que os microfones pertencem ao ADC ES7210, com MCLK=GPIO16,
BCLK=GPIO41, LRCK=GPIO45 e DIN=GPIO42. O firmware foi corrigido para essa rota,
incluindo a alimentação MIC VDD/BLDO2 em 3,3 V.

Na captura válida, sincronizada pelo visor por 8 s, foram recebidos 128.000
frames estéreo. O canal selecionado mediu RMS AC `329,005`, pico `2.974`,
3.495 valores distintos e clipping `0`. O ASR large-v3-turbo transcreveu:
`Teste Safety Field, teste de áudio, teste de gravação de áudio do Safety Field.`
com confiança `0,766`. Assim, o controle independente demonstra que voz normal,
captura PCM16, transporte USB/WAV e ASR produzem sinal útil quando alimentados
por um microfone operacional.

Evidência:
`evidence/mvp_operational/watch_mic_control_20260908/capture_voice_es7210_01/`.
SHA-256 do WAV mono:
`617D16574E97086F55600F3C4AE6F5BD928B443A8A4288E9082985B832EB0C70`.

Esse A/B reforça a classificação **E — MICROPHONE SUSPECT** para o INMP441 ou
seu caminho acústico interno, sem alterar o TP4 ou inferir falha a partir da
tentativa ES8311 zerada.

Com alimentação desligada, realizar um único A/B substituindo o módulo por um
INMP441 conhecido como bom, mantendo exatamente VDD=3,3 V, GND, L/R=GND e os
pins 41/42/43. Continuidade elétrica e porta livre não testam o transdutor MEMS
nem o caminho acústico interno; por isso não excluem esta causa.

Arquivos principais: `voice_gain8.wav`, `quiet_gain8.wav`, `right_quiet.wav`,
`gain8_voice_vs_quiet.png`, `voice_gain8.json`, `right_quiet.json`,
`asr_turbo_raw.json`, logs de build/programação e restauração nesta pasta.
