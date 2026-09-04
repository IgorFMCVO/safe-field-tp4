# UART bidirecional SAFE-FIELD TP4

## Pi -> Tang

UART 115200 8N1, idle HIGH, LVCMOS33. Pacote fixo de 11 bytes:

| Offset | Campo | Valor |
|---:|---|---|
| 0..1 | sync | `A6 6A` |
| 2 | versão | `01` |
| 3 | comando | `01` square16; `02` read BRAM; `03` average |
| 4..5 | sequence | little-endian |
| 6..9 | payload | little-endian, 32 bits |
| 10 | checksum | CRC-8/ATM sobre bytes 2..9 |

CRC: polinômio `0x07`, inicial `0x00`, sem reflexão ou XOR final. Frame
inválido é rejeitado e latched no status; não dispara operação aritmética.

## Tang -> Pi

O frame de telemetria v1 fisicamente aprovado continua com 16 bytes. Uma
resposta de comando usa o overlay:

- `flags[7]=1`: response;
- `flags[6]=1`: command error;
- `flags[5]=1`: CRC/framing error recebido;
- `energy[23:16]`: command ID;
- `energy[15:0]`: command sequence;
- `frame_counter[31:0]`: resultado numérico.

A resposta usa o mesmo TX package pin 39 já validado. A telemetria periódica
retoma no frame seguinte.

## Pin RX documentado

Tang package pin 46 é `IOT13B/LPLL_C_in`, Bank 1. No esquemático 3603,
`VCCO1` está ligado a 3,3 V e o net é `CAMERA_SDA`, com pull-up externo de
4,7 kΩ. A câmera permanece desconectada, portanto o net pode ser usado como
entrada UART com idle HIGH sem contenção.

Ligação futura, somente com placas desenergizadas:

`Raspberry physical pin 8 / GPIO14 TXD -> Tang package pin 46 / CAMERA_SDA`

O GND compartilhado existente deve permanecer. Não programar o build acadêmico
antes dessa ligação ser confirmada.

Fonte oficial: <https://dl.sipeed.com/fileList/TANG/Nano%204K/HDK/02_Schematic/Tang_Nano_4K_3603_Schematic_.pdf>
