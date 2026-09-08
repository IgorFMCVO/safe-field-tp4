# Arquitetura final SAFE-FIELD TP5

```mermaid
flowchart LR
  MIC[INMP441 / front-end I2S] -->|SD| FPGA[Tang Nano 4K - GW1NSR-4C]
  FPGA -->|SCK + WS| MIC
  PI[Raspberry ARM64] -->|UART TX / cmd + seq + payload + CRC| FPGA
  FPGA -->|UART TX / response + flags + CRC| PI
  PI -->|GPIO17 baseline| FPGA
  FPGA --> LED[LED / observabilidade]
  FPGA --> DSP[Q1.15 + FP16 + energia/FSM]
  DSP --> TEL[Telemetria e contadores]
  TEL --> PI
  PI --> CORE[SAFE-FIELD Core / armazenamento / MVP]
  CORE --> WEAR[Wearable / interface]
```

## Separacao de responsabilidades

A Tang executa aquisicao I2S, processamento numerico deterministico, FSM, validacao de protocolo, CRC, contadores e telemetria. O Raspberry executa bibliotecas ARM64, syscalls Linux, parsing, buffers, registro, medicao e integracao com o Core. O wearable e a IA permanecem acima do enlace embarcado e nao substituem a decisao deterministica do FPGA.

## Hardware real

O enunciado cita Raspberry Pi Zero 2 W como plataforma-alvo. A bancada disponivel usa Raspberry Pi 4 Model B com Raspberry Pi OS 64-bit; ambos executam AArch64 e mantem a mesma interface logica. O relatorio declara explicitamente essa adaptacao, sem afirmar que o Pi 4 e o Zero 2 W fisicamente identicos.
