# Protocolo ARM<->FPGA TP5

## Transporte coexistente RAW24 + comandos

O fluxo acústico aprovado permanece o produtor prioritário do UART TX: pacotes
RAW24 de 95 bytes (`A5 C4`, versão `01`, tipo `21`, CRC-16/CCITT-FALSE em
bytes 2..92), a 1.500.000 baud e divisor `CLKS_PER_BIT=18` no clock de 27 MHz.
O receptor de comandos usa o mesmo divisor no pino RX 46. Um comando recebido
enquanto um pacote RAW24 está em curso fica retido pelo `command_valid`; a
resposta só toma posse do TX depois do stop bit do byte 94. O RAW24 volta a
admitir o próximo pacote após a resposta de 12 bytes. Assim não há muxagem no
meio de uma palavra UART nem dois drivers no pino 39.

**Estado observado na imagem final:** RAW24 FPGA->Pi e comandos Pi->FPGA foram verificados fisicamente. Probe limpo: 2650 frames, resposta válida, flags `0x94`, `rx_low_seen=true`, sem checksum/framing/I²S/overrun; PING + 3 operações confirmaram sequência e CRC.

O atraso adicional máximo de uma resposta é um pacote RAW24 restante (95
bytes) mais a própria resposta (12 bytes). A aquisição I²S e as duas banks de
RAW24 não são pausadas por comandos; se a reserva exceder a capacidade do
transporte, o contador/flag de overrun continua explícito no pacote RAW24.

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
