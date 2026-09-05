# Auditoria de runtime de IA e captura física

Data da auditoria: 2026-09-05 (America/Sao_Paulo).

## Resultado objetivo

O núcleo de captura contínua, segmentação e fila assíncrona está implementado e
validado por replay. O ASR local pt-BR foi provisionado e validado em CPU/int8.
A ligação TP4 aprovada entrega apenas telemetria, mas uma variante MVP separada
foi construída e validada fisicamente para PCM contínuo. Em SRAM, a revalidação
final entregou 2.530.688 samples em 60,010637 s sem CRC, formato, resync
pós-lock, perdas, descontinuidades, frame errors ou overrun. O gate
`PHYSICAL_WATCH_PCM_003` gravou 421.760 samples em `raw.wav`, fechou a UART
antes do WAV e gerou histórico lifecycle-only vazio por meio de um utilitário
Python que usa o contrato START/STOP; não houve toque físico no wearable. As janelas não
tiveram fala controlada, portanto ASR/diarização acústicos físicos ainda não
podem ser declarados.

## Evidência do transporte existente

- `raspberry/safe_field_uart_protocol.py` define frame UART v1 fixo de 16 bytes:
  sequência, estado QUIET/ACTIVE, energia de 24 bits, contador de frames, flags e
  CRC-8/ATM.
- `raspberry/safe_field_hw_bridge.py` decodifica somente esses campos e grava
  JSONL. Não existe campo PCM nem reconstrução de WAV.
- A variante `verilog_mvp/pcm_stream` não reabre nem invalida o TP4: usa build e
  bitstream separados e foi programada somente em SRAM.

## Raspberry auditada por SSH

No snapshot inicial de 2026-09-05 10:49:11 -03:

- host: `safe-field`;
- `arecord -l`: exibiu apenas o cabeçalho, sem dispositivo ALSA de captura;
- Core aprovado ativo: `safe_field_core.py`, porta 8765;
- bridge aprovado ativo: `safe_field_hw_bridge.py`, `/dev/serial0`, 115200 baud.

Esse bridge foi depois interrompido deliberadamente para liberar a UART ao
stream PCM de 1,5 Mbaud; a linha acima não descreve o estado posterior.

Não há entrada ALSA alternativa na Raspberry. O caminho efetivamente validado
é o stream UART PCM Tang→Pi a 1,5 Mbaud.

## Razer / IA local

- GPU detectada: NVIDIA GeForce RTX 4090 Laptop GPU, 16.376 MiB;
- driver: 551.95; CUDA indicada pelo driver: 12.4;
- Faster-Whisper `1.2.1` e CTranslate2 `4.8.2` instalados em venv ignorada;
- modelo `faster-whisper-small` armazenado localmente em diretório ignorado;
- ASR validado: CPU/int8, 16/16 WAVs, voz pt-BR WER médio 0,0922;
- tentativa GPU bloqueada explicitamente: `cublas64_12.dll` ausente;
- stress com vozes en-US forçadas a português: WER médio 0,4241, FAIL mantido;
- PyTorch/torchaudio CPU 2.8.0 e SpeechBrain 1.0.3 provisionados localmente;
- ECAPA-TDNN local: 3/3 cenários, re-ID 1,000, zero merges/splits;
- tentativa local CRDNN-VAD + ECAPA: single-speaker 3/3, mas multi-speaker
  somente 1/3; não integrada ao runtime;
- pipeline completo de diarização multi-speaker: não provisionado;
- nenhum áudio, ocorrência ou conteúdo DIAO foi enviado a serviço externo.

## Gates

| Gate | Estado | Evidência |
|---|---|---|
| Escrita contínua de `raw.wav` por replay | PASS | testes do núcleo |
| Silêncio não interrompe captura global | PASS | teste dedicado |
| Segmentação com pre/post-roll | PASS | testes do núcleo |
| Captura PCM física FPGA→Raspberry | PASS | 60,010637 s; 2.530.688 samples; 79.084 frames; todos os erros/perdas/descontinuidades = 0 |
| Contrato START→captura contínua→STOP sobre UART física | PASS | utilitário Python; `PHYSICAL_WATCH_PCM_003`; 421.760 samples no WAV; histórico vazio; invariantes PASS |
| Wearable físico operacional START→STOP | PENDENTE | firmware compilado e contrato 25/25; não gravado/testado nesta rodada |
| ASR pt-BR real, autônomo | PASS | Faster-Whisper small CPU/int8; WER pt-BR 0,0922 |
| ASR sobre áudio físico com fala | FAIL/BLOCKED | janela física validou transporte, mas não continha fala controlada |
| Speaker embedding/re-ID neural | PASS controlado | ECAPA 192D; 4/4, 3/3, 3/3; re-ID 1,000; 0 merges/splits |
| Diarização multi-speaker | FAIL/BLOCKED | tentativa local passou 1/3; falta segmentação validada de mudança/overlap de locutor |
| Falha segura | PASS | `PROCESSING_PENDING`, fonte preservada |

## Próximo gate físico

O collector PCM validado está conectado ao lifecycle START/STOP e esse caminho
foi exercitado contra hardware por utilitário. O transporte Pi→Razer está
implementado e testado em loopback, mas sua implantação LAN/TLS permanece
pendente. Não se solicita nova participação do operador enquanto faltar a
diarização local. Depois desse provisionamento e da implantação, resta uma única
janela final: wearable autenticado START, fala controlada, confirmação,
orientação DIAO e STOP.
