# GATE A — DEBUG6 retest after contact repair

> O reteste ocorreu após correção física dos contatos dos pins 41 e 43.

## Resultado

**PASS físico por GAO/JTAG.** A correção física alterou o resultado observado.
As conclusões anteriores de `SD` estático/morto e de módulo INMP441 suspeito são
históricas, anteriores ao reparo, e estão explicitamente superadas para o estado
atual da montagem.

- Dispositivo JTAG: `GW1NSR-4C`, IDCODE `0x0100981B`.
- Programação: operação 2, `SRAM Program`; Flash não utilizada.
- GPIO17: `17: op -- pd | lo`, saída LOW.
- SCK medido internamente: `500000.0 Hz`.
- WS medido internamente: `7812.5 Hz`.
- Estrutura: 64 SCK/frame, 32 SCK/slot.
- Captura PCM LEFT: 1024 samples reais.
- Samples zero/não-zero: 0 / 1024.
- Mínimo/máximo: -9736 / +3078.
- Média: -4240.244140625.
- Média absoluta: 4509.189453125.
- RMS: 5276.146903976779.
- Pico absoluto: 9736.
- Transições SD na janela bruta: 8.
- Erros de frame: 0.

## Evidências

- `debug6_environment_01_core0_window0.csv`
- `debug6_environment_01_core1_window0.csv`
- `debug6_environment_01_analysis.json`
- `debug6_environment_01_gao.log`
- `debug6_sram_program_absolute.log`
- `debug6_build_console.log`

Observação: os contadores de atividade de 16 bits já estavam saturados quando o
GAO foi armado; os valores decisivos acima vêm das amostras brutas e dos sinais
capturados. O contador de frame errors permaneceu em zero.
