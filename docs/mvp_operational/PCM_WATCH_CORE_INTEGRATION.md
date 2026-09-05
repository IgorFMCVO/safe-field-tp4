# PCM UART → WATCH lifecycle integration

## Resultado

`PCM_WATCH_CORE_INTEGRATION = PASS` em testes sem hardware.

A integração é aditiva e não altera o TP4 congelado. O launcher operacional
aceita `--pcm-port`; quando ausente, o Core mantém exatamente o modo anterior de
injeção de PCM por software. Quando presente, configura:

- protocolo `UART_PCM16_V1`;
- 1.500.000 baud, abertura serial exclusiva;
- mono, signed PCM16 little-endian;
- taxa exata de origem 42.187,5 samples/s;
- cabeçalho WAV inteiro em 42.188 samples/s.

## Semântica transacional

1. WATCH `START` cria os artefatos da ocorrência e tenta abrir a serial.
2. START só retorna sucesso após a abertura. Falha de porta retorna conflito
   explícito, restaura `STANDBY` e preserva a ocorrência como `START_FAILED`.
3. O reader decodifica frames válidos e chama `core.ingest_pcm()` continuamente.
4. WATCH `STOP` interrompe e aguarda o reader antes de fechar `raw.wav`.
5. Se a fonte não puder parar, a API responde `409`, registra
   `PCM_SOURCE_STOP_FAILED`, mantém lifecycle/metadata em `ACTIVE` e deixa o
   recorder aberto; um novo STOP repete a tentativa sem perder bytes em trânsito.
6. Depois de a fonte ficar quiescente, o recorder fecha exatamente uma vez. Se
   o snapshot final indicar `error_free=false`, `STOPPED_WITH_ERRORS` ou qualquer
   contador crítico diferente de zero, a API responde HTTP 200 com `ok=false`,
   `state=CAPTURE_FAILED`, `lifecycle_state=STOPPING`,
   `reason=PCM_TRANSPORT_FAILED`, `retryable=false`,
   `finalization_pending=false` e `finalization_blocked=true`. A captura fica
   encerrada, a ocorrência e todos os artefatos permanecem disponíveis, mas
   nenhum histórico é publicado e a metadata fica `FINALIZATION_BLOCKED`.
7. Um STOP repetido nesse estado devolve o mesmo bloqueio sem parar a fonte ou
   fechar o WAV novamente. O erro pertence à captura já encerrada e não pode ser
   apagado por retry; a ocorrência permanece retida para decisão operacional.

O estado ao vivo aparece em `pcm_source` na rota
`GET /api/v1/operational/wearable/state`. O snapshot final é gravado em
`audio/pcm_transport.json`, incluindo `valid_frames`, `samples_received`,
`crc_errors`, `format_errors`, `discarded_bytes`, `sequence_losses`,
`sample_losses`, `i2s_frame_error_packets`, `transport_overrun_packets`,
`read_errors`, `sink_errors` e `last_error`.
`startup_alignment_discarded_bytes` preserva os bytes encontrados antes do
primeiro sync ao abrir um stream já ativo. `resync_discarded_bytes` conta apenas
perda de alinhamento posterior. O campo `error_free` exige zero erros, perdas e
ressincronizações, sem transformar o alinhamento inicial esperado em falha.
Falsos candidatos a sync antes do primeiro frame são contabilizados em
`startup_candidate_errors` sem serem confundidos com corrupção pós-lock. Depois
do lock, duplicatas, regressões ou resets de sequência/contador aparecem como
`sequence_discontinuities`/`sample_discontinuities` e falham o gate.
O Core também verifica diretamente CRC, formato, resync pós-lock, perdas,
descontinuidades, flags I²S/overrun e erros de leitura/sink; portanto a
finalização continua fail-closed mesmo se uma implementação de `PCMSource`
calcular incorretamente o campo agregado `error_free`.
Durante esse bloqueio, o endpoint wearable mantém `state=CAPTURE_FAILED` e
`lifecycle_state=STOPPING`; ele não o normaliza para `PROCESSING_PENDING`, pois
uma perda já ocorrida não será corrigida quando a fila drenar.

Falhas assíncronas não esperam o operador tocar STOP. `SerialPCMSource.status()`
expõe `reader_alive` e `quiescent`; assim que read ou sink falha, o endpoint
wearable muda imediatamente para `state=CAPTURE_FAILED`, preservando
`lifecycle_state=ACTIVE`, a ocorrência e o WAV aberto. Enquanto a thread ainda
está desenrolando, `capture_active=true` evita afirmar prematuramente que toda
entrega cessou. Quando `quiescent=true`, o mesmo estado passa a
`capture_active=false`. Nada é finalizado automaticamente: o STOP explícito
fecha/persiste a captura uma única vez e aplica o gate de integridade descrito
acima.

## Verificação executada

```powershell
.\mvp\evidence\local_ai_venv\Scripts\python.exe `
  -m unittest discover -s mvp\tests -p "test_*.py" -v

.\mvp\evidence\local_ai_venv\Scripts\python.exe `
  -m unittest discover -s raspberry_mvp\pcm_stream\tests -p "test_*.py" -v
```

- regressão completa do Core/API: PASS, 77/77;
- protocolo/receiver serial: PASS, 13/13;
- START/STOP e pacote final antes do fechamento: PASS;
- rollback de falha ao abrir porta: PASS;
- falha ao parar fonte mantém recorder aberto: PASS;
- CRC/formato/perdas/read/sink bloqueiam história e `FINISHED`: PASS;
- STOP repetido após falha de integridade é idempotente e permanece bloqueado:
  PASS;
- read/sink assíncronos aparecem no watch antes de STOP, com quiescência real:
  PASS;
- modo sem fonte PCM: PASS.

O transporte físico separado possui evidência final endurecida de 60,010637 s
com 2.530.688 samples e zero CRC/perdas/flags. O contrato START→recording→STOP
foi exercitado por um utilitário Python contra a UART física: 13.180 pacotes /
421.760 samples em `raw.wav`, fechamento ordenado e os contadores de erro em
zero. Isso valida o contrato de lifecycle e o transporte físico, não um toque
real no wearable. Como a janela não continha fala, foram fechados zero segmentos
e o histórico gerado contém apenas lifecycle/telemetria, sem conteúdo semântico.

## Verificação física final do transporte com o código endurecido

Sem reprogramar a FPGA e sem reiniciar o bridge antigo, o software atualizado
foi executado na Raspberry:

| Gate | Resultado |
|---|---:|
| Ocorrência | `PHYSICAL_WATCH_PCM_003` |
| START / STOP via utilitário do mesmo contrato | `ACTIVE` → `STANDBY`, PASS |
| Pacotes / samples | 13.180 / 421.760 |
| Frames no `raw.wav` | 421.760 |
| Razão observado/esperado | 0,999727 |
| Startup alignment / startup candidates | 43 / 0 bytes |
| Resync pós-lock | 0 bytes |
| CRC / formato | 0 / 0 |
| Perdas seq/sample | 0 / 0 |
| Descontinuidades seq/sample | 0 / 0 |
| Frame error / overrun / read / sink | 0 / 0 / 0 / 0 |
| Invariantes | nenhuma falha |
| Acceptance | PASS |

O WAV tem 416.729 samples não-zero, 427 valores distintos, mínimo -198,
máximo 231 e RMS 42,2250. Hashes:

- `raw.wav`: `728F11A9BE2BF0B8FA778BDAB6849AEC77231DA1BB199AFC68A67762EBCF3F1F`;
- relatório JSON: `D04FB943A4CD26597D91118DBD0CE57B6BFD6D81DA2F14267E3102CF83C867D3`;
- pacote ignorado: `655B7988C53A0D2AF35B3C558762E6829FACCD587497413E7BC13EAB72F873D1`.

A repetição contínua `physical_stability_60s_v2` recebeu 79.084 pacotes e
2.530.688 samples em 60,010637 s, razão 0,999778, sem alinhamento inicial,
resync, erro, perda ou descontinuidade. Hash do WAV:
`F52CC060B6E9D4BF7406AD21D7999F865C5D61B56124FE80A5AFAE46B5D2BFE3`;
hash do pacote ignorado:
`E1808B6C0BE24A16F804E1BCD04BB679C7509832B8B53260FA938EFC27819A90`.

`PHYSICAL_PCM_LIFECYCLE_CONTRACT = PASS`.

O wearable operacional v1 foi compilado e seu contrato passou 25/25 testes,
mas esse firmware não foi gravado nem usado nesta medição física.
