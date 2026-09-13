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

## Estado dos gates fisicos (13/09/2026)

Concluidos: programacao SRAM, smoke FPGA->Pi RAW24 (3966 frames/63456 amostras em 3 s, CRC/perdas/frame errors 0), ensaios nativos do Pi 4 e sentido Pi->FPGA. Probe limpo: 2650 RAW24, resposta valida, flags `0x94`, `rx_low_seen=true`, checksum/framing/I2S/overrun zero. PING + 3 operacoes, CRC rejection/recovery, burst 100/100 e estabilidade final 600 s passaram.

## Gate fisico final restante

Executar uma unica sessao apos instalar um microfone funcional:

- manter a imagem SRAM final e registrar fotos/terminal autorizados;
- validar GPIO17->Tang->LED;
- executar PING ARM->FPGA->ARM;
- enviar vetores Q15 e FP16 reais pela UART;
- manter a duracao de estabilidade definida pelo projeto, sem chamar o smoke de 3 s de estabilidade;
- registrar frames, sequence, CRC errors, framing errors e perdas;
- capturar audio real e comprovar variacao voz/silencio;
- medir round-trip UART com `clock_gettime`;
- salvar fotos, terminal e hashes.

Os gates físicos acima estão PASS. Permanecem somente a geração do PDF/ZIP e o vídeo de defesa, que não são testes de hardware.
