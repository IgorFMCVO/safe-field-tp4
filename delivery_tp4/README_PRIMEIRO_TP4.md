# LEIA PRIMEIRO — SAFE-FIELD TP4

Aluno: Igor de Freitas Monteiro  
Data da consolidação: 04/09/2026

## Resultado central

O TP4 demonstra em hardware real:

`som físico -> INMP441 -> I2S -> Tang Nano 4K -> energia/FSM -> LED/GPIO`

Resultado físico: **PASS** para alimentação, clocks, SD, reconstrução de
samples, resposta a voz e palmas, ausência de frame errors e integração GPIO17.
A estabilização final da FSM passou em simulação/replay de capturas físicas; a
última recaptura GAO com os parâmetros finais permanece claramente indicada
como residual, sem ser apresentada como PASS físico.

## Comece por estes arquivos

1. `docs/TP4_FINAL_VALIDATION_SUMMARY.md` — conclusão, métricas e ressalvas.
2. `docs/AUDIO_ACCEPTANCE_REPORT.md` — matriz detalhada dos gates físicos.
3. `MANIFESTO_ENTREGA_TP4.md` — mapa do conteúdo entregue.
4. `CHECKLIST_ENTREGA_TP4.md` — itens concluídos e pendências reais.
5. `bitstream/safe_field_tp4_validated.fs` — bitstream congelado.
6. `HASHES_SHA256.txt` — integridade de todos os arquivos do pacote.

## Bitstream oficial do TP4

- arquivo: `bitstream/safe_field_tp4_validated.fs`;
- dispositivo: Tang Nano 4K / GW1NSR-4C;
- SHA-256:
  `5D8F2D31EF5D0349AC0E52F13AC8A7472FCB1A23103131D13163BB8946F39181`;
- programação física usada: somente SRAM; nenhuma Flash foi gravada.

## Pinout congelado

| Sinal | Package pin | Direção |
|---|---:|---|
| `pi_signal` | 40 | Raspberry -> FPGA |
| `i2s_sck` | 41 | FPGA -> INMP441 |
| `i2s_ws` | 42 | FPGA -> INMP441 |
| `i2s_sd` | 43 | INMP441 -> FPGA |
| `sys_clk` | 45 | clock 27 MHz -> FPGA |
| `led` | 10 | FPGA -> LED |

Não alterar conexões com o hardware energizado. A câmera DVP permaneceu
fisicamente desconectada durante o TP4.
