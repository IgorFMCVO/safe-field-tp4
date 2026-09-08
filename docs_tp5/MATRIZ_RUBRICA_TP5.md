# Matriz da rubrica TP5

| Rubrica | Evidencia planejada/implementada |
|---|---|
| Arquitetura ARM-FPGA completa | `ARQUITETURA_FINAL_TP5.md`, top Verilog e bibliotecas ARM64 |
| Assembly modular, biblioteca estatica, Makefile, macros, strings/buffers e conversoes | `assembly_tp5/` completo + `libsafe_field_tp5.a` gerada pelo Makefile |
| Handshaking, comandos, telemetria e erros | `sf_command_rx.v`, `sf_telemetry_tx.v`, CRC-8/ATM e protocolo documentado |
| Ponto fixo e flutuante | `sf_fixed_q15_mac.v`, `sf_fp16_mul.v`, `tb_arithmetic.v` |
| IO/OE | pinout CST + `sf_gpio_oe.v` + `tb_gpio_oe.v` |
| Syscalls Linux ARM | `io_syscalls.S` + executavel stand-alone |
| Desempenho/estabilidade | plano automatizado + gate fisico final de 10 min e RTT |
| Documentacao final | relatorio PDF/MD, arquitetura, protocolo, checklist e roteiro de video |
| Video <=5 min | roteiro pronto em `ROTEIRO_VIDEO_TP5_5MIN.md`; gravacao fisica e upload sao operacoes finais do aluno |
