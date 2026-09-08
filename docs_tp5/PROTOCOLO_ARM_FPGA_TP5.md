# Protocolo ARM<->FPGA TP5

## ARM -> FPGA (11 bytes)

| Byte | Conteudo |
|---:|---|
|0|0xA6 sync 1|
|1|0x6A sync 2|
|2|0x05 versao TP5|
|3|command_id|
|4|sequence MSB|
|5|sequence LSB|
|6..9|payload32 big-endian|
|10|CRC-8/ATM de bytes 2..9|

Handshaking interno: o parser mantem `command_valid` ate `command_ready`. Um novo comando nao sobrescreve uma resposta pendente.

## FPGA -> ARM (12 bytes)

| Byte | Conteudo |
|---:|---|
|0|0x5A sync 1|
|1|0xA5 sync 2|
|2|0x05 versao|
|3|event/command type|
|4..5|sequence|
|6..9|data32|
|10|flags|
|11|CRC-8/ATM de bytes 2..10|

## Comandos finais

- `0x01 PING`: retorna `0x54503501`.
- `0x10 Q15_MUL`: payload = A[15:0] || B[15:0].
- `0x11 FP16_MUL`: payload = A(binary16) || B(binary16).
- `0x20 GET_GOOD_COMMANDS`.
- `0x21 GET_AUDIO_ENERGY`.
- `0x22 GET_CRC_ERRORS`.
- `0x23 GET_FRAMING_ERRORS`.

## Erros

CRC invalido nao gera comando valido e incrementa o contador de CRC. Framing error da UART e contado separadamente. Comando desconhecido retorna `0xFFFFFFFF` e flag de erro.
