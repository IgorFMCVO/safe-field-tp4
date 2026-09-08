# Plano de testes TP5

## Automatizados antes do hardware

1. Compilar top-level Verilog.
2. Testar Q1.15: positivo, negativo, limite e saturacao.
3. Testar FP16: normal, sinal, zero, overflow, NaN e subnormal/underflow.
4. Testar CRC valido e invalido no parser UART.
5. Testar OE/tri-state.
6. Compilar todos os modulos Assembly AArch64.
7. Gerar `libsafe_field_tp5.a`.
8. Linkar executavel stand-alone sem libc.
9. Executar em QEMU AArch64 e validar stdout/syscalls.
10. Gerar objdump.

## Gate fisico final

Executar uma unica sessao apos instalar um microfone funcional:

- programar TP5 em SRAM;
- validar GPIO17->Tang->LED;
- executar PING ARM->FPGA->ARM;
- enviar vetores Q15 e FP16 reais pela UART;
- manter 10 minutos de telemetria continua;
- registrar frames, sequence, CRC errors, framing errors e perdas;
- capturar audio real e comprovar variacao voz/silencio;
- medir round-trip UART com `clock_gettime`;
- salvar fotos, terminal e hashes.

Nenhum PASS fisico novo deve ser registrado antes desta sessao.
