# Pinout as-built confirmado

Confirmação fornecida pelo responsável em 03/09/2026. A montagem foi feita com
as placas desenergizadas.

| Net FPGA | Pino INMP441 | Package pin Tang Nano 4K | Direção |
|---|---|---:|---|
| `i2s_sck` | SCK | 41 (`IOT20A/GCLKT_1`) | FPGA -> microfone |
| `i2s_ws` | WS | 42 (`IOT20B/GCLKC_1`) | FPGA -> microfone |
| `i2s_sd` | SD | 43 (`IOT17A/GCLKT_0`) | microfone -> FPGA |

Conexões adicionais confirmadas:

- INMP441 VDD -> Tang 3V3; INMP441 GND -> Tang GND.
- INMP441 L/R -> GND por ponte local no módulo: canal LEFT.
- Raspberry GPIO17/physical pin 11 -> Tang package pin 40.
- Raspberry GND/physical pin 9 -> Tang GND.

## Verificação documental

- O esquema oficial Tang Nano 4K 3603 identifica 41, 42 e 43 como pads IOT de
  Bank 1 e liga `VCCO1` a `DCDC2_3V3`.
- As funções `GCLKT/GCLKC` são capacidades alternativas de entrada de clock;
  os pads continuam sendo I/O geral e aceitam as direções definidas pelo top.
- O esquema também roteia 41/42/43 ao conector de câmera como
  DVP_PCLK/DVP_HSYNC/DVP_VSYNC. Não são funções internas ativas, mas nenhum
  módulo de câmera pode permanecer conectado durante o uso do INMP441.
- O relatório de package pins da Gowin para o part number real confirma Bank 1,
  VCCIO 3,3 V e sites `IOT20[A]`, `IOT20[B]`, `IOT17[A]`.

## Confirmação pós-implementação

O relatório final `build/full/impl/pnr/safe_field_tp4.rpt.txt` confirmou:

- pino 41: `i2s_sck`, `out`, `IOT20[A]/GCLKT_1`, LVCMOS33, 8 mA,
  Bank VCCIO 3,3 V;
- pino 42: `i2s_ws`, `out`, `IOT20[B]/GCLKC_1`, LVCMOS33, 8 mA,
  Bank VCCIO 3,3 V;
- pino 43: `i2s_sd`, `in`, `IOT17[A]/GCLKT_0`, LVCMOS33, pull-down,
  Bank VCCIO 3,3 V.

O pull-down interno evita deixar a entrada FPGA indefinida durante o slot
RIGHT em alta impedância. O datasheet recomenda 100 kOhm externo em SD; antes
do ensaio físico, verificar se o módulo já o contém. O pull interno não deve ser
registrado como substituto eletricamente caracterizado para esse resistor.

Referência oficial:
<https://dl.sipeed.com/fileList/TANG/Nano%204K/HDK/02_Schematic/Tang_Nano_4K_3603_Schematic_.pdf>
