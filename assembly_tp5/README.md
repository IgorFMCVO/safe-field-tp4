# Assembly ARM64 TP5

Projeto AArch64 em multiplos modulos, com biblioteca estatica `libsafe_field_tp5.a` e executavel stand-alone sem libc.

## Modulos

- `io_syscalls.S`: `write` e `clock_gettime` via Linux AArch64 syscalls;
- `buffer.S`: limpeza de buffer e ring buffer;
- `parse.S`: texto->u64 e u64->texto;
- `arithmetic.S`: Q1.15 e soma 128-bit com `ADDS/ADC`;
- `protocol.S`: CRC-8/ATM e montagem do frame ARM->FPGA;
- `main.S`: demonstracao stand-alone.

## Build e teste

```bash
make
make test
make disasm
```

O `make test` usa QEMU AArch64 quando executado fora do Raspberry. No Raspberry Pi OS 64-bit o mesmo binario pode ser executado nativamente.
