# Verificação documental dos package pins 41, 42 e 43

Data: 03/09/2026

## Fontes cruzadas

1. Esquema oficial Sipeed `Tang_Nano_4K_3603_Schematic_.pdf`.
2. Relatório local da ferramenta Gowin V1.9.11.03 para
   `GW1NSR-LV4CQN48PC6/I5`, previamente gerado na baseline validada.
3. Pinout oficial Gowin UG865 listado para o GW1NSR-4C/QN48P.

## Resultado

| Package pin | Site/função alternativa | Banco/tensão | Rota da placa | Uso TP4 | Compatível |
|---:|---|---|---|---|---|
| 41 | `IOT20A/GCLKT_1` | Bank 1 / 3,3 V | DVP_PCLK | saída SCK | SIM |
| 42 | `IOT20B/GCLKC_1` | Bank 1 / 3,3 V | DVP_HSYNC | saída WS | SIM |
| 43 | `IOT17A/GCLKT_0` | Bank 1 / 3,3 V | DVP_VSYNC | entrada SD | SIM |

O esquema liga o pino de alimentação `VCCO1` do banco a `DCDC2_3V3`. Os nomes
GCLK indicam recursos opcionais de clock de entrada e não reservam os pads. Os
sinais DVP apenas conectam esses pads ao conector de câmera; sem câmera conectada
não há outro driver ativo.

Direções escolhidas:

- 41: FPGA -> INMP441 SCK, LVCMOS33, DRIVE=8, sem pull.
- 42: FPGA -> INMP441 WS, LVCMOS33, DRIVE=8, sem pull.
- 43: INMP441 SD -> FPGA, LVCMOS33, pull-down interno para o intervalo high-Z.

Risco residual obrigatório antes de programar: confirmar que o conector DVP não
tem módulo de câmera ou outra fonte conectada a PCLK/HSYNC/VSYNC.

Fontes oficiais:

- <https://dl.sipeed.com/fileList/TANG/Nano%204K/HDK/02_Schematic/Tang_Nano_4K_3603_Schematic_.pdf>
- <https://www.gowinsemi.com/en/document/main/database/400/?order=DESC&page=1&support_search=&type=category>
