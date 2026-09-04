# SAFE-FIELD TP4 — log de diagnóstico físico

Execução em 03/09/2026, fuso America/Sao_Paulo. Checkpoint isolado:
branch `tp4-physical-validation`, derivada do commit de diagnósticos `28bb261`.
A baseline e o build final de produção não foram sobrescritos.

## Estado confirmado antes do teste

- Tang Nano 4K conectada por USB/JTAG FT2232H.
- Raspberry Pi 4 acessível em `safe-field.local`.
- INMP441 alimentado em 3,3 V, medição física informada pelo responsável: PASS.
- Câmera DVP fisicamente desconectada.
- As-built mantido: GPIO17/40, SCK/41, WS/42, SD/43, clock/45 e LED/10.
- Nenhum fio, solda, alimentação ou conexão foi alterado durante esta execução.

## Fase 1 — interfaces reais

- `programmer_cli --scan --cable-index 1`: PASS, um dispositivo
  `GW1NSR-4C`, ID `0x0100981B`, cabo `Gowin USB Cable(FT2CH)`.
- Gowin Programmer CLI: V1.9.11.03 Education.
- SSH: PASS após autenticação interativa; a senha não foi persistida.
- `pinctrl set 17 op dl`: executado.
- `pinctrl get 17`: `17: op -- pd | lo // GPIO17 = output`, às
  `2026-09-03T22:18:36-03:00`.

Evidências: `phase1_gowin_scan.log`,
`phase1_raspberry_ssh_pinctrl.log` (tentativa BatchMode sem credencial) e
`phase1_raspberry_gpio17_low.log` (sucesso interativo sanitizado).

## Fase 2 — GAO/JTAG

A instalação contém `gao_analyzer.exe`, `gao_sh.exe`, IP `GAO`, inserção RTL
e os bridges específicos GW1NSR-4C. O manual local SUG114-3.4E documenta
captura Standard, programação SRAM, JTAG FT2CH e exportação CSV. Foi criado um
top separado, `safe_field_tp4_gao`, com a função de produção inalterada e
observabilidade passiva.

Núcleo 0, amostrado por `sys_clk`: SCK, WS, SD, strobe, bit index,
`sample_valid`, canal e erro de frame. Núcleo 1, amostrado por frame: sample
signed, magnitude, energia, FSM, andamento da janela e contadores saturantes.

### Build GAO

- Simulação da instrumentação: PASS, 11 checks, 0 erros.
- Síntese: PASS.
- P&R: PASS.
- STA: PASS, setup 0, hold 0; `sys_clk` requerido 27,000 MHz e Fmax
  32,260 MHz; `i2s_ws_clk` declarado como ÷640 = 42,1875 kHz.
- Recursos: Logic 1458/4608 (32%), registradores 1472/3573 (42%),
  CLS 1276/2304 (56%), BSRAM 6/10 (60%), I/O 10/39 (inclui quatro portas
  JTAG inseridas pelo GAO).
- Bitstream descritivo:
  `C:\SAFE-FIELD\fpga\tp4-audio-inmp441\build\physical_gao\impl\pnr\safe_field_tp4_physical_gao.fs`.
- Arquivo efetivamente passado ao Programmer:
  `C:\SAFE-FIELD\fpga\tp4-audio-inmp441\build\physical_gao\impl\pnr\ao_0.fs`;
  a cópia descritiva acima é byte a byte idêntica.
- SHA-256:
  `64A06F844FF63560384455ADA08B7F0C768BBA6A818579F87BDC5F6993968E56`.

### Warnings GAO — 70, nenhum ocultado

- 1 × `NL0002`: wrapper combinacional `rasp_to_tang` achatado, igual ao build
  final; o caminho GPIO17 permanece no netlist/LED.
- 66 × `PA1001`: seis carries não consumidos no comparador do receptor e
  sessenta bits/estados não usados nos módulos gerados do GAO/JTAG/BSRAM.
- 2 × `TA1117`: a ferramenta não calcula relação de análise cruzada entre
  `sys_clk` e o clock derivado `i2s_ws_clk`; ambos estão declarados e seus
  domínios individuais passam. O núcleo por frame é somente instrumentação.
- 1 × `PR1014`: rota genérica parcial de `sys_clk_d`, warning já conhecido do
  build final. A rede aparece como PRIMARY e o domínio de 27 MHz fecha a
  32,260 MHz no pior modelo.

### Programação SRAM

1. Operação 4, `SRAM Program and Verify`: download chegou a 100%, mas o
   readback terminou `Verify Failed`, exit 18. Registrado como tentativa FAIL,
   não como PASS.
2. Operação 2, `SRAM Program`: download 100%, exit 0, User Code `0x00002B72`,
   Status Code `0x0003F020`. PASS de programação confirmado funcionalmente
   pelas exportações GAO subsequentes. Nenhuma operação de Flash foi usada.

Logs: `gao_sram_program.log` e `gao_sram_program_op2.log`.

## Fase 3 — capturas físicas e estímulos

O Razer enviou ao dispositivo de reprodução padrão WAV mono de 48 kHz, 16 bits,
amplitude digital de 12% de full scale: 500 Hz, 1 kHz, 2 kHz e pulsos de 1 kHz.
Também foi feita captura sem reprodução. O comando de reprodução executou sem
erro; a pressão acústica no local do microfone não foi medida por instrumento
independente.

| Estímulo | SCK | WS | transições SD | `sample_valid` no trace | erros de frame | samples não-zero / 512 | magnitude máx. | energia máx. | ACTIVE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| sem reprodução | 2,700 MHz | 42,1875 kHz | 0 | 3 | 0 | 0 / 512 | 0 | 0 | 0 / 512 |
| tom 500 Hz | 2,700 MHz | 42,1875 kHz | 0 | 3 | 0 | 0 / 512 | 0 | 0 | 0 / 512 |
| tom 1 kHz | 2,700 MHz | 42,1875 kHz | 0 | 3 | 0 | 0 / 512 | 0 | 0 | 0 / 512 |
| tom 2 kHz | 2,700 MHz | 42,1875 kHz | 0 | 3 | 0 | 0 / 512 | 0 | 0 | 0 / 512 |
| pulsos 1 kHz | 2,700 MHz | 42,1875 kHz | 0 | 3 | 0 | 0 / 512 | 0 | 0 | 0 / 512 |

Em todas as capturas por frame, `sample_valid_toggle` e
`frame_valid_toggle` mudaram 511 vezes e `energy_update_toggle` mudou duas
vezes em 512 frames. Portanto receptor e janela de 256 frames avançaram; a
energia zero é consequência dos samples zero, não de FSM parada.

Os CSVs `gao_*_core0_window0.csv` e `gao_*_core1_window0.csv` são dados lidos
do FPGA real por JTAG. Os `gao_*_analysis.json` são resumos reproduzíveis deles.

## PASS/FAIL por camada

| Camada | Resultado físico | Evidência |
|---|---|---|
| A. gerador interno SCK/WS | PASS | divisores medidos 10 e 640: 2,700 MHz / 42,1875 kHz |
| B. SD no input buffer do pin 43 | FAIL | 0 transições em seis capturas, inclusive sob quatro estímulos |
| C. `sample_valid` | PASS | pulsos no trace de `sys_clk`; toggle por frame avança |
| D. `sample_data` não-zero | FAIL | 0/512 em todas as cinco condições finais |
| E. magnitude | FAIL como consequência | magnitude máxima 0 |
| F. janela/média | PASS de avanço, entrada zero | dois updates/512 frames; energia 0 |
| G. threshold/FSM | NÃO É A CAUSA ATUAL | QUIET é correto para energia 0 |

## Conclusão e causa provável

O problema foi localizado antes do parsing: o input buffer FPGA do package pin
43 vê SD permanentemente LOW. Threshold, média e histerese não explicam a
falha. SCK/WS existem no domínio interno, o receptor emite samples no ritmo
correto e a janela/FSM avança sem erros de frame.

A causa componente exata ainda não pode ser distinguida sem observação física
adicional. Hipóteses compatíveis: SCK/WS não chegam aos pads do módulo apesar
de serem gerados/roteados pelo FPGA; descontinuidade ou solda em SD; módulo
INMP441 defeituoso/orientado incorretamente; ou linha SD presa a GND. O startup
não explica: as capturas ocorreram muito depois dos ~97 ms correspondentes a
2^18 ciclos de SCK.

Próxima ação indispensável, somente com procedimento físico seguro: medir SCK
e WS nos pads do INMP441 e SD no pad/pin 43 com osciloscópio/analisador; depois,
com tudo desenergizado, testar continuidade e inspecionar soldas/orientação.
Nenhuma dessas ações foi executada autonomamente porque exigiria tocar/medir o
hardware energizado ou desmontar a ligação.

## Recomendação

- Manter `safe_field_tp4_physical_gao.fs` em SRAM durante o diagnóstico: é o
  bitstream mais observável e reproduziu a falha diretamente.
- Não calibrar thresholds enquanto SD/samples forem zero.
- Depois de corrigir a camada SD, repetir GAO silêncio/tom. Só então usar
  `DEBUG_LOW_THRESHOLD` para calibração e retornar ao build final de produção.
- O build final preservado continua em
  `build\full\impl\pnr\safe_field_tp4.fs`, SHA-256
  `0B04C9DF3F51B408932ED75B754F7F180001F02C50594B14CC685B4CE1BFFE8B`.

## Comandos essenciais executados

```powershell
ssh -tt -o StrictHostKeyChecking=accept-new safe-field@safe-field.local "pinctrl set 17 op dl; pinctrl get 17; date --iso-8601=seconds"
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gw_sh.exe' 'C:\SAFE-FIELD\fpga\tp4-audio-inmp441\scripts\build_physical_gao.tcl'
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\Programmer\bin\programmer_cli.exe' --scan --cable-index 1
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\Programmer\bin\programmer_cli.exe' --device GW1NSR-4C --operation_index 4 --frequency 2.5MHz --fsFile 'C:\SAFE-FIELD\fpga\tp4-audio-inmp441\build\physical_gao\impl\pnr\ao_0.fs' --cable-index 1
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\Programmer\bin\programmer_cli.exe' --device GW1NSR-4C --operation_index 2 --frequency 2.5MHz --fsFile 'C:\SAFE-FIELD\fpga\tp4-audio-inmp441\build\physical_gao\impl\pnr\ao_0.fs' --cable-index 1
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gao_sh.exe' -gao 'C:\SAFE-FIELD\fpga\tp4-audio-inmp441\src\safe_field_tp4_gao.rao' -out '<capture-prefix>' -device GW1NSR-4C -cable FT2CH -location 0
& 'C:\SAFE-FIELD\fpga\tp4-audio-inmp441\scripts\run_physical_audio_stimuli.ps1'
& 'C:\SAFE-FIELD\fpga\tp4-audio-inmp441\scripts\verify_physical_evidence.ps1'
```

## 04/09/2026 — DEBUG5_EXTERNAL_WIRING_LEVELS

Objetivo: verificar fisicamente, sem alterar a montagem, se os package pins 41
e 42 chegam aos pads SCK e WS do INMP441. A variante é independente dos builds
anteriores e não executa o protocolo I2S: mantém níveis estáticos complementares
por intervalos de 2 s, adequados a medição com multímetro ou osciloscópio.

### Resultado de software e implementação

| Etapa | Resultado | Evidência |
|---|---|---|
| simulação | PASS, 29/29 checks | `debug5_external_wiring_levels/simulation_2026-09-04T10-49-50-868Z.log` |
| síntese | PASS | `debug5_external_wiring_levels/build_console.log` |
| Place & Route | PASS | `build/debug5_external_wiring_levels/impl/pnr/debug5_external_wiring_levels.rpt.txt` |
| STA | PASS, 0 setup/hold | `build/debug5_external_wiring_levels/impl/pnr/debug5_external_wiring_levels.tr` |
| scan JTAG | PASS, GW1NSR-4C ID `0x0100981B` | `debug5_external_wiring_levels/jtag_scan.log` |
| GPIO17 | PASS, output LOW | `debug5_external_wiring_levels/gpio17_low.log` |
| SRAM Program | PASS, 100%, exit 0 | `debug5_external_wiring_levels/sram_program.log` |
| medição nos pads | PENDENTE | exige observação física do usuário |

O P&R confirma: pin 41 `out` LVCMOS33/8 mA; pin 42 `out` LVCMOS33/8 mA;
pin 43 exclusivamente `in` LVCMOS33 com pull-down; pin 40 `in`; pin 45 `in`;
pin 10 `out` LVCMOS18. A câmera permaneceu fisicamente desconectada.

Warnings preservados e analisados:

1. `CV0016`: `i2s_sd` é propositalmente não usado no DEBUG5. A porta continua
   listada no relatório P&R como `in`, sem drive; isso não afeta SCK/WS.
2. `PR1014`: roteamento genérico conhecido em `sys_clk_d`. A rede é PRIMARY;
   STA desta variante passa a 27 MHz com Fmax 121,483 MHz.

Bitstream programado somente em SRAM:
`C:\SAFE-FIELD\fpga\tp4-audio-inmp441\build\debug5_external_wiring_levels\impl\pnr\debug5_external_wiring_levels.fs`

SHA-256:
`712A05C5102B2D61895761769C386D6521D34BBFBB386F7B33A6B9294380C3D6`

Programação iniciada em `2026-09-04T07:51:21.1492175-03:00` e finalizada em
`2026-09-04T07:51:23.4526979-03:00`. Operação Programmer 2, `SRAM Program`;
nenhuma operação de Flash foi executada.

Comandos exatos (a senha SSH foi digitada interativamente e não foi gravada):

```powershell
node 'sim\run-debug5.mjs'
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gw_sh.exe' 'scripts\build_debug5_external_wiring_levels.tcl'
Get-FileHash -Algorithm SHA256 -LiteralPath 'build\debug5_external_wiring_levels\impl\pnr\debug5_external_wiring_levels.fs'
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\Programmer\bin\programmer_cli.exe' --scan --cable-index 1
ssh -tt -o StrictHostKeyChecking=accept-new safe-field@safe-field.local "pinctrl set 17 op dl; pinctrl get 17; date --iso-8601=seconds"
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\Programmer\bin\programmer_cli.exe' --device GW1NSR-4C --operation_index 2 --frequency 2.5MHz --fsFile 'C:\SAFE-FIELD\fpga\tp4-audio-inmp441\build\debug5_external_wiring_levels\impl\pnr\debug5_external_wiring_levels.fs' --cable-index 1
```

Resultado físico ainda não atribuído: aguardar as leituras LOW/HIGH nos pads
SCK/WS. Não inferir continuidade a partir da simulação ou da programação.
