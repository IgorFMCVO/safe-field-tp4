# MVP PCM stream — build validation

Data local do build final estabilizado: 05/09/2026 11:17:36 (America/Sao_Paulo).

## Resultado

| Gate | Resultado | Evidência |
|---|---|---|
| Packet protocol simulation | PASS | `simulation.log`: framing, payload signed, sequência, CRC, filtro LEFT e zero perda |
| Sustained physical-rate simulation | PASS | 320 samples, 10 pacotes, divisor UART 18, zero overrun |
| Python protocol/collector tests | PASS (13/13) | CRC conhecido, round-trip, resync/corrupção, continuidade, descontinuidades, falhas assíncronas read/sink, WAV vazio/inválido e aceitação fail-closed |
| Synthesis | PASS | `build/mvp_pcm_stream/impl/gwsynthesis/safe_field_mvp_pcm_stream.log` |
| Place & Route | PASS | `build/mvp_pcm_stream/impl/pnr/safe_field_mvp_pcm_stream.log` |
| STA | PASS | 0 setup violations, 0 hold violations, TNS 0 |
| Bitstream | PASS, programado somente em SRAM | arquivo, SHA e gate físico abaixo |

Comandos executados:

```powershell
node .\verilog_mvp\pcm_stream\sim\run_pcm_stream.mjs
python `
  -m unittest discover -s raspberry_mvp\pcm_stream\tests -p 'test_*.py' -v
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gw_sh.exe' `
  .\verilog_mvp\pcm_stream\scripts\build_mvp_pcm_stream.tcl
```

O Gowin V1.9.12.03 comercial foi tentado primeiro e recusou a licença; nenhum
artefato válido veio dessa tentativa. O build válido usa V1.9.11.03 Education.

Após o build, o receiver/verificador foi endurecido sem alterar RTL ou
bitstream: captura vazia e duração inválida falham, `samples = frames × 32` é
obrigatório, startup/resync são separados e duplicata/regressão/reset possuem
contadores fail-closed. A suíte final do receiver passou 13/13 testes. O mesmo
bitstream foi revalidado por WATCH por 10 s e continuamente por 60,010637 s com
todos esses gates em zero; detalhes e hashes estão em
`evidence/mvp_operational/physical_pcm_transport/PHYSICAL_PCM_TRANSPORT_REPORT.md`.

## Timing e utilização

- device: `GW1NSR-LV4CQN48PC6/I5` / GW1NSR-4C;
- sys_clk requerido: 27,000 MHz;
- Fmax alcançado: 35,984 MHz;
- pior slack de setup listado: +9,247 ns;
- setup/hold endpoints violados: 0/0;
- logic: 1348/4608 (30%);
- registers: 1502/3573 (43%);
- CLS: 1633/2304 (71%);
- I/O: 8/39 (21%).

## Warnings revisados (7)

1. Seis `PA1001` para `n7_1_SUM` até `n12_1_SUM` no `i2s_rx_24`. São saídas
   intermediárias de carry otimizadas sem consumidor. Os mesmos identificadores
   aparecem nos builds I2S fisicamente validados anteriores; os ports e a lógica
   útil permanecem roteados.
2. Um `PR1014` informa uso de routing genérico para `sys_clk_d`. Também aparece
   nos builds validados anteriores. Não foi mascarado: o clock está constrangido,
   o report mostra PRIMARY global, Fmax 35,984 MHz para requisito 27 MHz e zero
   violações. Portanto não impede este gate, mas permanece registrado.

Não há warnings de porta sem uso, conflito de pinagem, latch ou truncamento.

## Bitstream separado

```text
C:\SAFE-FIELD\fpga\tp4-audio-inmp441\build\mvp_pcm_stream\impl\pnr\safe_field_mvp_pcm_stream.fs
SHA-256: F46314D4A3478B6157A5253DF07E2AAB2022D305EA16E94E0F9F9A8706C0EC7B
size: 1168345 bytes
```

Após concluir simulação/P&R/STA, o Programmer Education executou operação 2
(SRAM Program) a 100%. A Flash não foi acessada.

## Gate físico

No Raspberry auditado, `/dev/serial0` aponta para `ttyS0` (mini UART) e foi
confirmado em `B1500000`. O teste final do lifecycle WATCH recebeu 13.180
frames e 421.760 samples, com CRC, formato, resync pós-lock, perdas,
descontinuidades, frame errors e overruns todos em zero. A estabilidade v2
recebeu 79.084 frames / 2.530.688 samples em 60,010637 s, também sem erros.
Evidência:
`evidence/mvp_operational/physical_pcm_transport/PHYSICAL_PCM_TRANSPORT_REPORT.md`.
