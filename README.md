# SAFE-FIELD TP4

Entrega acadêmica de Sistemas Digitais Embarcados com Tang Nano 4K
GW1NSR-4C e Raspberry Pi 4.

## Resultado

- rubrica: 22/22 PASS;
- áudio físico INMP441 -> FPGA: PASS;
- DSP `MULT18X18` e BSRAM `SDPB`: PASS;
- Assembly AArch64, NEON inteiro e NEON float: PASS no Raspberry Pi 4;
- UART FPGA -> ARM e ARM -> FPGA: PASS físico;
- três comandos numéricos: expected = actual;
- checksum errors: 0;
- sequence losses: 0.

## Estrutura

- `verilog_tp4/`: RTL, testbenches, constraints, builds e evidências;
- `assembly_tp4/`: Assembly AArch64, NEON, testes e logs;
- `docs_tp4/`: relatório PDF, arquitetura, resultados e evidências.

Relatório final: `docs_tp4/output/pdf/RELATORIO_TECNICO_SAFE_FIELD_TP4.pdf`.

Vídeo: https://youtu.be/1Ancm5QdG2E
