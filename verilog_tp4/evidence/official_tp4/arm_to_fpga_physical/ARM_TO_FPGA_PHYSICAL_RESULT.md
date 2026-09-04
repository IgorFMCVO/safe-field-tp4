# ARM -> FPGA physical acceptance

Data: 04/09/2026. Hardware: Raspberry Pi 4 Model B e Tang Nano 4K
GW1NSR-4C. Câmera DVP desconectada. GND compartilhado.

## Ligação confirmada pelo operador

- Raspberry physical pin 8 / GPIO14 / TXD -> Tang package pin 46 / IOT13B;
- Tang package pin 39 / TX -> Raspberry physical pin 10 / GPIO15 / RX.

## Pré-voo

- JTAG: GW1NSR-4C, ID `0x0100981B`;
- `/dev/serial0 -> /dev/ttyS0`;
- GPIO14 = TXD1; GPIO15 = RXD1; GPIO17 = LOW;
- serial getty inativo; usuário no grupo `dialout`; pyserial 3.5.

## Defeito lógico encontrado e correção

Na primeira execução, dois comandos passaram e a terceira resposta expirou. A
telemetria continuou válida, isolando o defeito na arbitragem de resposta. Um
pulso de `telemetry_event_valid` podia ser perdido quando uma telemetria
periódica começava no mesmo ciclo. A variante acadêmica foi corrigida para
manter `event_valid` até `event_ready`. A baseline e o áudio não foram alterados.

## Build efetivamente programado

- caminho: `build/safe_field_tp4_official_bidirectional/impl/pnr/safe_field_tp4_official_bidirectional.fs`;
- SHA-256: `6E4C460162816C54EE38B11CDA246004C05FE07CEC4C1FA963FDBB36092E172F`;
- simulação: 40/40 PASS;
- P&R: PASS; STA: PASS; Fmax 38,297 MHz para 27 MHz;
- recursos: 1 `MULT18X18`, 1 `SDPB`;
- programação: operação 2, SRAM, 100%; Flash não utilizada.

## Resultado físico final

| Sequence | Operand | Expected | Actual | CRC | Resultado |
|---:|---:|---:|---:|---|---|
| 16641 | 123 | 15129 | 15129 | PASS | PASS |
| 16642 | -123 | 15129 | 15129 | PASS | PASS |
| 16643 | 32767 | 1073676289 | 1073676289 | PASS | PASS |

- valid telemetry frames observados durante o teste: 73;
- checksum errors: 0;
- sequence losses: 0;
- response errors: 0;
- **ARM -> FPGA: PASS físico**.

Evidências: `01_jtag_scan.log`, `02_sram_program.log` (primeira variante),
`03_gowin_build_console.log`, `04_fixed_sram_program.log`,
`05_raspberry_preflight.log` e `06_FPGA_PI_BIDIRECTIONAL.log`.
