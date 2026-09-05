# Gate estrutural: PCM FPGA → Raspberry

## Resultado de auditoria

O bridge fisicamente aprovado envia apenas telemetria de estado/energia a
115.200 baud; ele não contém PCM. A Raspberry auditada também não expõe um
dispositivo ALSA de captura. Logo, o pipeline de ASR não pode receber o áudio do
INMP441 por esse estado físico, embora a aquisição e telemetria TP4 estejam PASS.

## Variante separada implementada e validada

`verilog_mvp/pcm_stream` adiciona transporte contínuo PCM16 no mesmo TX já
validado (Tang package pin 39 → Raspberry GPIO15/pino físico 10), sem trocar
pinagem. A taxa muda para 1.500.000 baud exatos; a entrada reversa permanece no
pin 46, exclusivamente input, e a câmera permanece desconectada. Nada nesta
variante é gravado em Flash ou altera o TP4 congelado.

O pacote inclui sync, versão/tipo, sequência, contador absoluto de samples,
32 samples signed PCM16 e CRC-16/CCITT-FALSE. Há bancos ping-pong e indicadores
separados de frame error e overrun.

## Cálculo defensável

| Item | Valor |
|---|---:|
| Sample rate LEFT | 42.187,5 sample/s |
| PCM16 cru | 84.375 byte/s |
| UART 115.200, capacidade 8-N-1 | 11.520 byte/s |
| Requisito protocolado | 1.028.320,3125 bit/s |
| UART proposta | 1.500.000 bit/s exatos (`27 MHz / 18`) |
| Ocupação serial | 68,55% |
| Margem | 31,45% |

115.200 baud não é uma opção válida. A variante mantém todos os samples LEFT e
trunca somente os oito bits menos significativos de 24 para 16 bits; não introduz
decimação sem filtro antialias.

## Gate físico executado

Em 2026-09-05 a variante foi programada **somente em SRAM** e `/dev/serial0`
foi confirmado a 1.500.000 baud. Uma captura física de 10,021 s recebeu 13.180
frames e 421.760 samples com zero CRC errors, zero format errors, zero bytes
descartados, zero sequence/sample losses, zero frame errors e zero overruns.
O collector retornou código 0. A Flash permaneceu intocada.

Resultado: `PHYSICAL_PCM_TRANSPORT = PASS`.

Uma segunda captura contínua legada, preservada como evidência
pré-endurecimento, durou 60,0107 s e recebeu 79.083
frames / 2.530.656 samples. CRC, formato, sequência, contador de samples,
frame-error flags e overrun permaneceram em zero. A abertura encontrou 40 bytes
antes do primeiro sync; eles são registrados como alinhamento inicial esperado,
não como perda posterior. Não houve ressincronização depois do primeiro frame.

O mesmo stream foi então exercitado por um utilitário Python que chama o mesmo
contrato de lifecycle: START abriu a UART, `raw.wav` recebeu 421.760 samples e
STOP interrompeu o reader antes de fechar o WAV. Os contadores de erro ficaram
em zero. Isto não representa toque físico no wearable; sem fala nessa janela,
zero segmentos foram fechados e o histórico contém somente lifecycle/telemetria.

Resultado adicional: `PHYSICAL_PCM_LIFECYCLE_CONTRACT = PASS`.

## Repetição final após endurecimento do verificador

As evidências legadas acima foram preservadas. Para validar diretamente os
novos contadores e invariantes, os dois testes foram repetidos em 2026-09-05 sem
nova programação da FPGA:

- `PHYSICAL_WATCH_PCM_003`: 13.180 frames, 421.760 samples, 43 bytes apenas de
  alinhamento inicial, zero falso candidato, zero resync pós-lock, zero erro,
  perda ou descontinuidade, razão de taxa 0,999727 e invariantes PASS;
- `physical_stability_60s_v2`: 79.084 frames, 2.530.688 samples em 60,010637 s,
  zero startup/resync, zero erro, perda ou descontinuidade, razão de taxa
  0,999778 e acceptance PASS.

Pacotes locais ignorados e íntegros:

- WATCH: `655B7988C53A0D2AF35B3C558762E6829FACCD587497413E7BC13EAB72F873D1`;
- 60 s: `E1808B6C0BE24A16F804E1BCD04BB679C7509832B8B53260FA938EFC27819A90`.

O WAV contém dados reais do INMP441, mas a janela não teve fala controlada; ela
não é usada para declarar ASR acústico físico. Evidência detalhada:
`evidence/mvp_operational/physical_pcm_transport/PHYSICAL_PCM_TRANSPORT_REPORT.md`.
