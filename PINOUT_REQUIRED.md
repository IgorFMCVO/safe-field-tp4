# Confirmação física necessária antes do Place & Route

Os arquivos locais comprovam apenas o clock, GPIO17 e LED. A fiação soldada do
INMP441 não pode ser inferida por software. Antes de gerar/programar o bitstream,
registrar os números dos **package pins Gowin** conectados a:

| Net FPGA | Pino INMP441 | Package pin Tang Nano 4K | Direção |
|---|---|---:|---|
| `i2s_sck` | SCK | PENDENTE | FPGA -> microfone |
| `i2s_ws` | WS | PENDENTE | FPGA -> microfone |
| `i2s_sd` | SD | PENDENTE | microfone -> FPGA |

Também registrar:

- VDD do INMP441 em **3,3 V** (nunca 5 V) e GND comum.
- Estado soldado de L/R: GND = canal esquerdo, VDD = canal direito.
- Placa totalmente desenergizada antes de continuidade ou alteração de fios.
- Idealmente, foto nítida ou tabela as-built e continuidade com multímetro.

O arquivo `src/safe_field_tp4.cst` não contém LOCs fictícios. O script completo
`scripts/build_all_after_pinout.tcl` só deve ser executado após preencher e
revisar esses três LOCs.
