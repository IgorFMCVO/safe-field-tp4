# DEBUG5_EXTERNAL_WIRING_LEVELS

Variante diagnóstica isolada criada em 04/09/2026. Não altera nem sobrescreve
o build final, DEBUG1–4 ou GAO.

## Resultado

- Simulação: PASS, 29 checks, 0 erros.
- Síntese: PASS.
- Place & Route: PASS.
- STA: PASS; 0 endpoints violados em setup e hold; TNS 0/0; Fmax 121,483 MHz.
- Recursos: Logic 52/4608, registros 36/3573, CLS 28/2304, I/O 6/39.
- Warnings: 2 (`CV0016` e `PR1014`), ambos preservados no log e analisados em
  `STATUS_TP4.md`.
- JTAG: GW1NSR-4C, ID `0x0100981B`.
- Programação: SRAM Program (operação 2), 100%, exit code 0.
- Flash: não acessada.
- Medição física: PENDENTE.

## Bitstream

`C:\SAFE-FIELD\fpga\tp4-audio-inmp441\build\debug5_external_wiring_levels\impl\pnr\debug5_external_wiring_levels.fs`

SHA-256:
`712A05C5102B2D61895761769C386D6521D34BBFBB386F7B33A6B9294380C3D6`

## Níveis esperados

| Intervalo repetitivo | pin 41 / SCK | pin 42 / WS | LED lógico com GPIO17 LOW |
|---|---:|---:|---:|
| 2 s, fase 0 | LOW | HIGH | LOW |
| 2 s, fase 1 | HIGH | LOW | HIGH |

O ciclo completo dura 4 s. Pin 43 permanece exclusivamente INPUT LVCMOS33 com
pull-down e não é dirigido pela FPGA.
