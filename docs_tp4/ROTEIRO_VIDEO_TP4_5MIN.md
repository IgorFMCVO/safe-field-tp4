# Roteiro de vídeo SAFE-FIELD TP4 — 5 minutos

## 00:00–00:25 — identificação

- aluno/webcam: Igor de Freitas Monteiro;
- tela: `docs_tp4/video_demo/01_ARQUITETURA.png`;
- dizer: objetivo e hardware real Raspberry Pi 4 + Tang Nano 4K + INMP441.

## 00:25–01:00 — evolução e arquitetura

- mostrar `01_ARQUITETURA.png`;
- destacar caminho I2S, DSP, BSRAM, FSM e UART bidirecional;
- explicar que câmera/wearable são futuros e não mascaram o TP4.

## 01:00–01:40 — Verilog, DSP e BSRAM

- mostrar `02_VERILOG_BRAM_DSP.png` com o RTL e o uso real
  `SDPB=1`, `MULT18X18=1`.

## 01:40–02:10 — testbench e waveform

- mostrar `03_WAVEFORM.png`;
- dizer: 40/40 checks, inclusive CRC inválido rejeitado.

## 02:10–02:50 — funcionamento físico de áudio

- mostrar `07_AUDIO_PHYSICAL_PASS.png` nos valores RMS 4,99x,
  três palmas e `frame_errors=0`;
- mostrar o hardware/LED usando o registro físico existente, sem encenar GAO.

## 02:50–03:30 — Assembly ARM64

- mostrar `04_ARM64_NEON.png`, destacando `ADDS/ADC`, `SCVTF`, tabela,
  máscara, shift, `ROR`, `SMULL/UADALP` e `FMUL`.

## 03:30–04:05 — NEON e benchmark

- mostrar `05_BENCHMARK_NEON.png`;
- dizer os speedups do run 800: 3,273697x inteiro e 1,126641x float, sem
  esconder a variação dos demais runs.

## 04:05–04:35 — comunicação

- mostrar `06_FPGA_PI_BIDIRECTIONAL.log`;
- explicar Tang->Pi PASS: 3.264 mensagens e zero perdas;
- explicar Pi->Tang PASS: 3/3 operandos, expected=actual, CRC=0 e perdas=0.

## 04:35–05:00 — conclusão

- mostrar `08_FINAL_RESULTS.md`;
- mostrar a rubrica e o hash do `.fs` exibidos nessa tela;
- encerrar com 22/22 PASS e informar o link do vídeo publicado.

Vídeo gravado: https://youtu.be/1Ancm5QdG2E
