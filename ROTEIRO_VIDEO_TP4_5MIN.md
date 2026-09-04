# Roteiro de vídeo SAFE-FIELD TP4 — 5 minutos

## 00:00–00:25 — identificação

- aluno/webcam: Igor de Freitas Monteiro;
- tela: `docs_tp4/ARQUITETURA_TP4.md`;
- dizer: objetivo e hardware real Raspberry Pi 4 + Tang Nano 4K + INMP441.

## 00:25–01:00 — evolução e arquitetura

- mostrar os dois diagramas Mermaid;
- destacar caminho I2S, DSP, BSRAM, FSM e UART bidirecional;
- explicar que câmera/wearable são futuros e não mascaram o TP4.

## 01:00–01:40 — Verilog, DSP e BSRAM

- abrir `verilog_tp4/rtl/safe_field_audio_energy_dsp.v`;
- abrir `verilog_tp4/rtl/safe_field_energy_bram.v`;
- abrir `verilog_tp4/build/.../safe_field_tp4_official.rpt.txt` nas linhas de
  recurso: `SDPB=1`, `MULT18X18=1`.

## 01:40–02:10 — testbench e waveform

- mostrar `verilog_tp4/tb/tb_safe_field_tp4_official.v`;
- mostrar `docs_tp4/waveforms/dsp_expected_actual_waveform.png`;
- mostrar `docs_tp4/waveforms/uart_command_crc_waveform.png`;
- dizer: 40/40 checks, inclusive CRC inválido rejeitado.

## 02:10–02:50 — funcionamento físico de áudio

- mostrar `normal_voice_real_01_waveform_distribution.png` e
  `normal_claps_real_01_clap_amplitude_time.png`;
- mostrar `TP4_FINAL_VALIDATION_SUMMARY.md` nos valores RMS 4,99x,
  `frame_errors=0` e aquisição 99,42 s;
- mostrar o hardware/LED usando o registro físico existente, sem encenar GAO.

## 02:50–03:30 — Assembly ARM64

- abrir `assembly_tp4/safe_field_arm64.S`;
- destacar `ADDS/ADC`, `SCVTF`, tabela, máscara, shift e `ROR`;
- mostrar `safe_field_arm64_test.objdump.txt`.

## 03:30–04:05 — NEON e benchmark

- destacar `SMULL/SMULL2/UADALP` e `FMUL v1.4s`;
- mostrar `docs_tp4/ARM64_NEON_RESULTADOS.md`;
- dizer os speedups do run 800: 3,273697x inteiro e 1,126641x float, sem
  esconder a variação dos demais runs.

## 04:05–04:35 — comunicação

- mostrar JSONL físico do bridge e `MVP_HW_BRIDGE_STATUS.md`;
- explicar Tang->Pi PASS: 3.264 mensagens e zero perdas;
- mostrar `docs_tp4/UART_BIDIRECIONAL_TP4.md`;
- dizer honestamente que Pi->Tang aguarda o único fio pin8->pin46.

## 04:35–05:00 — conclusão

- mostrar `MATRIZ_RUBRICA_TP4.md` e `CHECKLIST_FINAL_TP4.md`;
- mostrar hash do `.fs`, PDF e ZIP;
- encerrar com resultados PASS e as duas pendências humanas: fio RX e gravação
  deste vídeo.

Gravação humana: **PENDENTE**. Este roteiro não é evidência de vídeo gravado.
