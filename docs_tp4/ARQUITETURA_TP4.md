# Arquitetura SAFE-FIELD TP4

```mermaid
flowchart LR
    MIC[Som fisico / INMP441] --> I2S[I2S 24-bit LEFT]
    I2S --> RX[Tang: receptor I2S]
    RX --> MAG[Magnitude e energia validada]
    RX --> DSP[DSP 16x16: sample²]
    DSP --> BRAM[BSRAM 256 x 32]
    BRAM --> AVG[Media de potencia]
    MAG --> FSM[FSM QUIET / ACTIVE]
    AVG --> RESP[Resultado consultavel]
    FSM --> TX[UART TX / telemetria CRC]
    RESP --> TX
    TX --> PI[Raspberry Pi 4 / SAFE-FIELD Core]
    PI --> RXUART[UART RX / comandos CRC]
    RXUART --> DSP
```

```mermaid
flowchart TB
    ARM[Raspberry Pi 4 AArch64] --> ASM[Assembly: add128, conversao, LUT, bits]
    ARM --> NINT[NEON inteiro: energia 8 lanes]
    ARM --> NFLOAT[NEON float: escala 4 lanes]
    ASM --> CORE[SAFE-FIELD Core]
    NINT --> CORE
    NFLOAT --> CORE
    CORE --> CAM[Camera UVC preparada / fora do caminho critico]
    CORE --> WEAR[Wearable HTTP preparado / evolucao futura]
    ARM <-->|UART 115200 8N1| FPGA[Tang Nano 4K]
```

## Evolução TP3 -> TP4

O caminho GPIO17 já validado permanece como override determinístico. O TP4
acrescenta aquisição acústica I2S real, processamento no FPGA, BSRAM e DSP
dedicados, telemetria com CRC, recepção de comandos numéricos e rotinas AArch64
com NEON. Câmera, wearable físico, transcrição, IA e transporte PCM completo
continuam fora do caminho crítico.

## Domínios preservados

- áudio final: `safe_field_tp4_validated.fs`, imutável;
- bridge FPGA->Pi: build separado e fisicamente aprovado;
- build acadêmico bidirecional: `safe_field_tp4_official_bidirectional.fs`,
  programado somente em SRAM e fisicamente aprovado;
- GPIO17, I2S e LED mantêm os package pins 40/41/42/43/45/10;
- RX acadêmico usa package pin 46 com câmera desconectada; 3/3 comandos físicos
  retornaram expected=actual, CRC=0 e perdas=0.
