# Arquitetura operacional do MVP SAFE-FIELD

## Escopo

Este documento especifica um núcleo novo e aditivo. O TP4, a FPGA validada, o
bridge UART e o firmware wearable existente permanecem inalterados. Câmera,
reconhecimento facial, biometria civil, culpa e decisão jurídica estão fora do
escopo.

O fluxo operacional é iniciado e encerrado explicitamente pelo operador:

```text
STANDBY
   │ START
   ▼
OCCURRENCE ACTIVE ── áudio PCM contínuo ──► audio/raw.wav
   │                         │
   │                         └─ segmentador fecha trechos por silêncio
   │                                      │
   │                                      ▼
   │                           fila assíncrona durável
   │                                      │
   │                         ASR → speakers → fatos → hipóteses
   │
   │ STOP
   ▼
fecha trecho → STOPPING → drena fila ── concluída ─► consolida
                          │                            │
                          │ timeout/falha              ▼
                          └─ FINALIZATION_PENDING   HISTORICO_PRELIMINAR
                               │ retry seguro           │
                               └─────────────────────────┘ → STANDBY
```

Nem o estado `QUIET/ACTIVE` da FPGA nem o detector de silêncio controlam a
gravação. Enquanto a ocorrência estiver ativa, cada frame PCM recebido é escrito
primeiro em `raw.wav`. O detector de silêncio só determina o fim de um segmento.

## Componentes

- `OperationalIntelligenceCore`: lifecycle START/STOP, captura e consolidação.
- `ContinuousAudioRecorder`: `raw.wav` contínuo e cópia de trabalho
  `processed.wav`; o original nunca é sobrescrito.
- `SilenceSegmenter`: pre-roll de 400 ms, post-roll de 400 ms e fechamento após
  1.500 ms de silêncio por padrão. Os valores são configuráveis e ainda exigem
  calibração com dados físicos.
- `AsyncSegmentPipeline`: fila não limitada, thread de trabalho e chamadas
  assíncronas de provedores. A captura nunca aguarda IA.
- `SpeakerRegistry`: registro isolado por ocorrência, múltiplos protótipos e
  política explícita para matches ambíguos.
- `FactGraph`: nós factuais rastreáveis e relações explícitas; IDs conflitantes
  nunca são sobrescritos silenciosamente.
- modelos `Fact` e `Hypothesis`: procedência e estado separados.
- `build_preliminary_history`: relatório cronológico derivado somente dos
  artefatos persistidos.

## Estrutura por ocorrência

```text
sessions/<occurrence_id>/
├── audio/
│   ├── raw.wav
│   └── processed.wav
├── segments/
├── transcripts/
├── speakers/
├── facts/
├── hypotheses/
├── guidance/
├── reports/
├── jobs/
├── timeline.jsonl
└── occurrence.json
```

Cada segmento possui WAV e sidecar JSON. Jobs malsucedidos recebem
`PROCESSING_PENDING`; o WAV de origem e o erro ficam preservados para replay.
A saída bruta do ASR é persistida imediatamente, antes de chamar diarização ou
embedding. Portanto, uma falha posterior preserva também `raw_transcript`,
confiança e referência ao áudio, ainda que `speaker_ids` permaneça vazio até a
diarização poder ser repetida.

## Concorrência e backpressure

`ingest_pcm()` executa somente escrita local do PCM e segmentação. O fechamento
de um trecho faz `put()` numa `SimpleQueue`, operação que não espera ASR,
diarização, embedding, reasoning, knowledge ou wearable. O worker consome os
jobs em paralelo à continuidade da gravação.

O MVP usa fila não limitada porque perda de evidência é pior que crescimento
temporário do backlog. Produção deve monitorar disco, profundidade da fila e
latências. Na indisponibilidade de um provedor, o job vira
`PROCESSING_PENDING`; nenhuma resposta operacional é inventada.

## Integração PCM aditiva

O Raspberry continua sendo collector/orchestrator. A variante separada
`verilog_mvp/pcm_stream` transporta PCM pela ligação Tang→Pi já existente, sem
alterar o TP4 congelado; o transporte passou o gate físico em SRAM. O argumento
opcional `--pcm-port` liga essa fonte ao ciclo WATCH: abertura transacional no
START e interrupção antes do fechamento do WAV no STOP. O Razer hospeda os
providers locais pesados. O protocolo privado Pi→Razer está implementado,
endurecido e validado em loopback com providers controlados; a implantação
LAN/TLS, o token efêmero e os modelos efetivos ainda estão pendentes. O mesmo
contrato de confirmação passou testes HTTP e do firmware wearable compilado,
mas o firmware operacional novo não foi gravado nem usado numa ocorrência
física. Esses limites não são escondidos por este MVP parcial.

## Finalização em duas fases

Quando `STOP` é solicitado em `ACTIVE`, o Core primeiro torna a fonte PCM
quiescente. Se `pcm_source.stop()` lançar, registra `PCM_SOURCE_STOP_FAILED`,
mantém lifecycle/metadata em `ACTIVE`, preserva ocorrência e `raw.wav` abertos e
não inicia consolidação; um novo `STOP` repete a tentativa. Somente após a fonte
confirmar a parada o Core muda para `STOPPING` e fecha o gravador exatamente uma
vez.

Antes de publicar histórico, o snapshot final do transporte é um gate
fail-closed. `error_free=false`, estado de erro ou qualquer CRC, formato, resync
pós-lock, perda, descontinuidade, frame error, overrun, read error ou sink error
mantém a sessão ligada ao Core com metadata `FINALIZATION_BLOCKED` e motivo
`PCM_TRANSPORT_FAILED`. A API/watch expõe o estado terminal da captura como
`CAPTURE_FAILED`, preservando `lifecycle_state=STOPPING`,
`finalization_blocked=true` e `retryable=false`; não o apresenta como trabalho
que terminará ao drenar. A captura já encerrada não é reaberta; um novo `STOP` é
idempotente, mas não apaga o erro e continua sem publicar histórico.

O mesmo diagnóstico é visível antes do STOP. A fonte serial publica
`reader_alive`/`quiescent`; uma falha assíncrona de read ou sink muda a resposta
watch para `CAPTURE_FAILED` imediatamente, sem mudar automaticamente o lifecycle
interno `ACTIVE`, fechar o WAV ou produzir histórico. `capture_active` só muda
para `false` depois de `quiescent=true`, eliminando tanto o falso “capturando”
após morte do reader quanto a declaração prematura durante uma entrega em voo.

Com transporte íntegro, o Core drena a fila. Se ela não concluir dentro do
timeout, a sessão permanece com metadata `FINALIZATION_PENDING`; nenhum
`HISTORICO_PRELIMINAR` é publicado. Um novo `STOP` é um retry de finalização e
não fecha nem duplica o áudio. Quando todos os jobs concluem sem falha, a
ocorrência é marcada como `FINISHED`, os dois históricos são gerados e somente
então as referências são liberadas e o Core retorna a `STANDBY`.

Uma falha efetiva de provider também impede a publicação do histórico. Nesse
caso o retorno explícito é `PROCESSING_FAILED_REQUIRES_REPLAY`; o job, a fonte e
qualquer transcrição já obtida permanecem em disco para recuperação deliberada.
