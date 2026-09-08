# SAFE-FIELD - Projeto de Bloco - TP5

Aluno: Igor de Freitas Monteiro  
Disciplina: Sistemas Digitais Embarcados

Esta etapa consolida o SAFE-FIELD em um prototipo final ARM64 + FPGA. O TP4 permanece congelado: todo o desenvolvimento desta etapa esta isolado em `verilog_tp5`, `assembly_tp5` e `docs_tp5`.

## Estrutura

- `verilog_tp5/`: RTL final, aritmetica Q1.15 e FP16, protocolo UART, telemetria, I2S, testbenches e constraints.
- `assembly_tp5/`: bibliotecas AArch64 estaticas, syscalls Linux, parsing, buffers, protocolo e executavel stand-alone.
- `docs_tp5/`: arquitetura, protocolo, rubrica, roteiro de video, checklist e relatorio tecnico.

## Estado de evidencia

A integracao UART bidirecional e o caminho FPGA/ARM possuem baseline fisica validada no TP4. O TP5 adiciona novos artefatos e testes automatizados. A recaptura fisica final de audio TP5 deve ser feita somente com um INMP441 funcional/substituto, pois o modulo atualmente em bancada esta sob suspeita fisica. Nenhuma evidencia fisica nova e inventada neste pacote.
