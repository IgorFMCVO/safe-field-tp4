# Raspberry PCM collector

Receiver separado para o build `mvp_pcm_stream`. Não substitui nem modifica o
bridge TP4 existente.

Teste offline:

```bash
python -m unittest discover -s raspberry_mvp/pcm_stream/tests -p 'test_*.py' -v
```

Comando de captura física (variante programada somente em SRAM):

```bash
python raspberry_mvp/pcm_stream/safe_field_pcm_receiver.py \
  --port /dev/serial0 --duration 10 --output sessions/pcm_transport_gate/raw.wav
```

Critério mínimo: `crc_errors=0`, `format_errors=0`,
`resync_discarded_bytes=0`, `sequence_losses=0`, `sample_losses=0`,
`sequence_discontinuities=0`, `sample_discontinuities=0`,
`i2s_frame_error_packets=0` e `transport_overrun_packets=0`. O collector também
exige contagens positivas e a invariável `samples = valid_frames × 32`.
O collector é fail-closed: ausência, tipo inválido, valor diferente de zero,
captura vazia, duração não positiva ou violação da invariável retorna falha.

Integração com WATCH/Operational Core (build PCM já programado em SRAM):

```bash
python raspberry/safe_field_core/safe_field_operational_server.py \
  --host 127.0.0.1 --port 8770 --pcm-port /dev/serial0
```

`SerialPCMSource` abre `/dev/serial0` somente no POST de START, entrega PCM16
decodificado ao `OperationalIntelligenceCore.ingest_pcm()` e é interrompido
antes do fechamento de `raw.wav` no POST de STOP. Falha ao abrir a UART rejeita
START sem deixar ocorrência ativa. Os contadores ficam na resposta/status
`pcm_source` e em `audio/pcm_transport.json` da sessão. O status também publica
`reader_alive` e `quiescent`: falha assíncrona de read/sink aparece
imediatamente como `CAPTURE_FAILED` no watch, e `capture_active` só muda para
falso depois que nenhuma entrega do reader permanece em voo. O Core não fecha
nem finaliza automaticamente a ocorrência; o STOP explícito preserva o WAV e
transforma o erro em bloqueio não retryable, sem gerar histórico.

Gate executado em 2026-09-05: 13.180 frames / 421.760 samples em 10,021 s,
todos os contadores de falha em zero, exit code 0. O WAV e os sidecars
permanecem em `mvp/evidence/physical_pcm_transport/`, caminho ignorado pelo Git;
o relatório sanitizado está em
`evidence/mvp_operational/physical_pcm_transport/PHYSICAL_PCM_TRANSPORT_REPORT.md`.

Gate de estabilidade adicional: 79.083 frames / 2.530.656 samples em 60,011 s,
sem erro ou perda. Gate físico pelo lifecycle WATCH: START→421.760 samples em
`raw.wav`→STOP→histórico final, também sem erro/perda. Bytes anteriores ao
primeiro sync são reportados separadamente como alinhamento inicial; qualquer
descarte após o primeiro frame é `resync_discarded_bytes` e falha o gate.

Após o endurecimento fail-closed, os gates foram repetidos sem reprogramar a
FPGA: `PHYSICAL_WATCH_PCM_003` obteve 13.180/421.760 e razão de taxa 0,999727;
a estabilidade `physical_stability_60s_v2` obteve 79.084/2.530.688 em 60,0106 s
e razão 0,999778. Em ambos, erros, perdas, resync e descontinuidades foram zero.
