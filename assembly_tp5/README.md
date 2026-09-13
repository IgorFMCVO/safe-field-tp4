# Assembly ARM64 TP5

Projeto AArch64 em multiplos modulos, com biblioteca estatica `libsafe_field_tp5.a` e executavel stand-alone sem libc.

## Modulos

- `io_syscalls.S`: `write` e `clock_gettime` via Linux AArch64 syscalls;
- `buffer.S`: limpeza de buffer e ring buffer;
- `parse.S`: texto->u64 e u64->texto;
- `arithmetic.S`: Q1.15 e soma 128-bit com `ADDS/ADC`;
- `protocol.S`: CRC-8/ATM, montagem ARM->FPGA e validação semântica FPGA->ARM;
- `main.S`: demonstracao stand-alone.

## Build e teste

```bash
make
make test
make disasm
```

`make test-offline` usa QEMU AArch64 e PTY quando executado fora do Raspberry:
isso valida o binário, CRC, recuperação e o contrato, mas não é evidência física.
No Raspberry Pi OS 64-bit, `run_on_pi.sh --tp5-physical-1m5-confirmed`
executa o mesmo cliente nativamente apenas depois de confirmar uma imagem física
compatível com TP5+RAW24 a 1.500.000 baud. O top acadêmico v05 de 115200 baud
não atende esse contrato sem reconstrução compatível.
