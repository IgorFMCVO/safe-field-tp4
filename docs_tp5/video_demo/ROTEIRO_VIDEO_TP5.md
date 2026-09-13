# Roteiro SAFE-FIELD TP5 — até 5 minutos

## 0:00–0:35 — problema e arquitetura

Mostrar `ARQUITETURA_FINAL_TP5.md`. Explicar: INMP441 fornece I²S 24-bit;
Tang executa captura e processamento determinístico; UART transporta RAW24 e
respostas; Raspberry Pi 4 real executa o cliente Assembly ARM64.

## 0:35–1:30 — FPGA e requisitos acadêmicos

Mostrar `safe_field_tp5_top.v`, `sf_fixed_q15_mac.v` e `sf_fp16_mul.v`.
Destacar handshake, CRC, sequence, saturação Q1.15, perfil binary16 e arbitragem
sem colisão com RAW24. Mostrar `BUILD_SUMMARY.md`: síntese/P&R/STA PASS,
Fmax 42,268 MHz, zero violações e bitstream hashado.

## 1:30–2:15 — testes Verilog

Mostrar `tp5_wasm_self_checking.log` e a waveform
`tb_tp5_raw24_coexist.vcd`: cinco testes PASS, incluindo 23 checks aritméticos,
CRC/recuperação, OE, 8 transações de integração e coexistência RAW24 + PING.

## 2:15–3:00 — Assembly ARM64 nativo

Mostrar `native_build_test_retry03.log`, `uart_client.S` e o ELF/objdump.
Declarar a plataforma corretamente: Raspberry Pi 4 Model B Rev 1.5, AArch64.
Resultado: stand-alone PASS, ABI 196/196 e cliente físico verificando PING +
três operações numéricas.

## 3:00–4:10 — bancada física e desempenho

Com webcam, mostrar Tang, Raspberry e INMP441 sem mover fios. Mostrar o probe
limpo e os artefatos `physical_raw24_smoke.log`, `tp5_uart_perf_probe20.json` e
`tp5_uart_stability_600s_retry02.json`. Explicar expected × actual, zero
erros/perdas, RTT/p95/throughput e os 600 s com RAW24.

## 4:10–4:40 — áudio físico

Mostrar a foto da ligação e `INMP441_ACOUSTIC_REVALIDATION_20260913.md`.
Relatar voz coerente e tom esperado/observado de 1.000 Hz, sem chamar a razão
espectral de SNR calibrado. A captura pessoal não é publicada.

## 4:40–5:00 — fechamento

Mostrar o PDF/ZIP finais, commit/CI e `PENDENTE_LINK_FINAL` para o vídeo.
Concluir que o TP5 integrou
I²S/RAW24, processamento FPGA e protocolo ARM↔FPGA na mesma imagem, preservando
o TP4 congelado.
