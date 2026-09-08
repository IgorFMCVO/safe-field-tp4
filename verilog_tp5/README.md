# Verilog TP5

Top-level: `rtl/safe_field_tp5_top.v`.

## Blocos finais

- I2S master + receptor signed 24-bit;
- detector de energia e FSM de atividade com histerese;
- UART RX/TX e protocolo TP5 com CRC-8/ATM;
- handshaking `command_valid/command_ready` e `event_valid/event_ready`;
- unidade de ponto fixo Q1.15 com saturacao;
- multiplicador floating-point IEEE-754 binary16 de escopo academico (subnormais flush-to-zero, documentado);
- celula de GPIO com OE/tri-state para validacao de direcao;
- telemetria minima de comandos, energia e contadores de erro.

## Simulacao

```bash
make test
```

Os testbenches sao auto-verificaveis e geram VCD em `build/`.

## Hardware

O pinout preserva a baseline fisica do TP4. O bitstream TP5 deve ser gerado no Gowin IDE para GW1NSR-4C e programado inicialmente em SRAM. Nao reutilizar um `.fs` TP4 como se fosse TP5.
