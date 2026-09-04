# STATUS TP4 — SAFE-FIELD / INMP441

Atualizado em 04/09/2026, fuso America/Sao_Paulo.

## Resumo executivo

O checkpoint `tp4-audio-inmp441` contém receptor I2S de 24 bits, geração de
SCK/WS, `sample_valid`, magnitude/média, FSM com histerese e integração com o
caminho GPIO17 -> LED preexistente. Simulação, síntese, Place & Route, STA e
geração do `.fs` passaram. O build final abaixo permanece byte a byte intacto.
Em 03/09/2026, o checkpoint separado `tp4-physical-validation` programou apenas
SRAM com GAO/JTAG e localizou a falha física na camada SD. Em 04/09/2026, a
branch `tp4-audio-acceptance` confirmou SCK/WS em baixa velocidade e demonstrou
que SD segue o pull interno do FPGA, permanecendo sem saída I2S do microfone.
O INMP441/estágio SD é o principal suspeito; áudio ainda não está operacional.

Bitstream revisado:
`C:\SAFE-FIELD\fpga\tp4-audio-inmp441\build\full\impl\pnr\safe_field_tp4.fs`

SHA-256:
`0B04C9DF3F51B408932ED75B754F7F180001F02C50594B14CC685B4CE1BFFE8B`

Bitstream GAO atualmente recomendado para diagnóstico em SRAM:
`C:\SAFE-FIELD\fpga\tp4-audio-inmp441\build\physical_gao\impl\pnr\safe_field_tp4_physical_gao.fs`

SHA-256 GAO:
`64A06F844FF63560384455ADA08B7F0C768BBA6A818579F87BDC5F6993968E56`

## DEBUG5_EXTERNAL_WIRING_LEVELS — PASS físico informado pelo operador

Em 04/09/2026 foi criada uma variante isolada para comprovar continuidade
externa de SCK/WS até os pads do INMP441. Nenhum fonte, bitstream ou diretório
de implementação anterior foi sobrescrito. A variante foi programada somente
em SRAM às 07:51:21 -03:00; a operação chegou a 100%, terminou com exit code 0
e confirmou o GW1NSR-4C ID `0x0100981B`.

- Simulação: PASS, 29 checks, 0 erros.
- Síntese: PASS.
- Place & Route: PASS.
- STA: PASS, 76 paths/73 endpoints, 0 violações setup/hold, TNS 0/0,
  pior setup +28,805 ns, pior hold +0,708 ns e Fmax 121,483 MHz para 27 MHz.
- Recursos: 52/4608 Logic (2%), 36/3573 registradores (1%), 28/2304 CLS
  (2%) e 6/39 I/O ports (16%).
- Warnings: 2. `CV0016` informa que `i2s_sd` não é usado pela lógica; o P&R
  ainda confirma pin 43 exclusivamente `in`, LVCMOS33, pull-down, sem drive.
  `PR1014` é o warning já conhecido de roteamento genérico de `sys_clk_d`; o
  clock foi promovido a PRIMARY e o STA passa com ampla margem nesta variante.
- Pin 41/SCK: `out`, LVCMOS33, alterna a cada 54.000.000 clocks = 2,000 s.
- Pin 42/WS: `out`, LVCMOS33, sempre inverso ao pin 41.
- Pin 43/SD: `in`, LVCMOS33, pull-down; nunca dirigido pelo DEBUG5.
- Pins preservados: GPIO17 pin 40 `in`, clock pin 45 `in`, LED pin 10 `out`.
- GPIO17 foi confirmado `output LOW` na Raspberry antes da programação.
- Comportamento esperado: 2 s com SCK LOW/WS HIGH, depois 2 s com SCK HIGH/WS
  LOW, repetindo em ciclo de 4 s; o LED indica a fase quando GPIO17 permanece
  LOW.

Bitstream DEBUG5 realmente programado:
`C:\SAFE-FIELD\fpga\tp4-audio-inmp441\build\debug5_external_wiring_levels\impl\pnr\debug5_external_wiring_levels.fs`

SHA-256 DEBUG5:
`712A05C5102B2D61895761769C386D6521D34BBFBB386F7B33A6B9294380C3D6`

Estado físico: **PASS informado explicitamente pelo operador em 04/09/2026**.
SCK e WS foram observados alternando LOW/HIGH nos pads do próprio INMP441. Esta
evidência confirma somente os caminhos externos de SCK/WS; não valida SD.

## Aceitação de áudio DEBUG6/DEBUG7 — bloqueada em SD

- DEBUG6: SCK=500.000 Hz, WS=7.812,5 Hz, 64 SCK/frame e 0 frame errors.
- GATE A: FAIL; pull-down resultou em 512/512 samples zero e 0 transições SD.
- DEBUG7 NONE: SD HIGH constante nos dois slots, 0 transições, 512 samples -1.
- DEBUG7 UP: SD HIGH constante nos dois slots, 0 transições, 512 samples -1.
- DEBUG7 UP + tom 1 kHz: resultado idêntico; nenhuma resposta acústica.
- Diagnóstico: SD está em alta impedância contínua ou circuito aberto, em vez
  de ser dirigido no slot LEFT. O módulo INMP441/saída SD é o principal
  suspeito; continuidade física de SD ainda é alternativa não distinguível.
- GATES C–G não foram executados porque dependem de samples reais.
- Nenhuma calibração ou threshold foi inventado.
- Após o teste UP, DEBUG6 com pull-down foi restaurado somente em SRAM.
- Relatório completo: `AUDIO_ACCEPTANCE_REPORT.md`.

## Validação física executada em 03/09/2026

- JTAG: PASS, GW1NSR-4C ID `0x0100981B` detectado.
- Raspberry: PASS, GPIO17 configurado e lido como output LOW.
- GAO build: simulação/P&R/STA PASS, 0 violações setup/hold.
- SRAM Program: PASS pela operação 2 (exit 0) e captura GAO subsequente; a
  tentativa anterior “Program and Verify” teve readback FAIL e foi preservada.
- SCK/WS internos: PASS, 2,700 MHz e 42,1875 kHz.
- `sample_valid` e janela de 256 frames: PASS, avançando sem erro de frame.
- `i2s_sd` no input do pin 43: FAIL, zero transições.
- Samples reais: FAIL, 0/512 não-zero em silêncio, 500 Hz, 1 kHz, 2 kHz e
  pulsos de 1 kHz; magnitude=0, energia=0, FSM=QUIET.
- Nenhum dos quatro bitstreams de LED foi necessário/programado: GAO forneceu
  evidência direta e mais forte da camada que falhou.
- Log completo: `evidence/physical/PHYSICAL_DIAGNOSTIC_LOG.md`.

## CONCLUÍDO

- Baseline física localizada em
  `C:\SAFE-FIELD\fpga\safe_field_tang_blink\safe_field_tang_blink`, auditada
  inicialmente em modo read-only e mantida fora do checkpoint de trabalho.
- Cópia byte a byte e repositório Git/branch `tp4-audio-inmp441` criados;
  `src/rasp_to_tang.v` do checkpoint permanece idêntico à baseline.
- Gowin Designer, Programmer e `gw_sh.exe` localizados. O build usa
  V1.9.11.03 Education, a mesma linha de ferramenta da baseline.
- Pinos 41/42/43 verificados no esquema oficial da Sipeed como I/O de Bank 1
  alimentado por 3,3 V e, depois do P&R, confirmados no relatório Gowin como
  LVCMOS33 e nas direções corretas.
- As-built registrado em `PINOUT_REQUIRED.md` e constraints aplicados em
  `src/safe_field_tp4.cst`.
- Master I2S: SCK 2,700 MHz, WS 42,1875 kHz, 32 SCK/slot e 64 SCK/frame.
- Receptor: 24 bits signed, complemento de dois, MSB-first, atraso I2S de 1 SCK,
  `sample_valid`, canal e erro de frame.
- Processamento: magnitude absoluta, máximo LEFT/RIGHT por frame, média de 256
  frames e FSM QUIET/ACTIVE com histerese (ON=50000, OFF=30000).
- Integração preservada: GPIO17 HIGH continua forçando LED; com GPIO17 LOW, a
  FSM de áudio controla a indicação.
- Simulação final: 42 checks unitários/protocolo + 17 checks ponta a ponta,
  total 59, 0 erros, PASS. Inclui silêncio, sinais positivos/negativos,
  limiares, histerese, valor mínimo signed, erros de bit/WS e GPIO17.
- Síntese: PASS. Place & Route: PASS. Geração de bitstream: PASS.
- Timing interno: PASS; 0 violações setup/hold, TNS 0/0, WNS setup +3,075 ns,
  pior hold +0,708 ns e Fmax 29,444 MHz para clock requerido de 27 MHz.
- Utilização final: 315/4608 Logic = 7% (274 LUT, 41 ALU), 147/3573
  registradores = 5%, 220/2304 CLS = 10%, 6/39 I/O = 16%.
- Todos os logs intermediários, experimento BUFG, relatórios finais e
  bitstreams de tentativas foram preservados em `evidence/` e `build/full/`.

## Warnings finais — 2

1. `WARN (NL0002)`: a hierarquia trivial `rasp_to_tang/gpio17_baseline` foi
   achatada pela otimização. Não significa remoção funcional do caminho: a
   lógica combinacional integra o OR do LED e passou no teste ponta a ponta.
2. `WARN (PR1014)`: roteamento genérico no trecho de entrada de `sys_clk_d`
   pode causar atraso/skew. O pino 45 é `LPLL_T_in`; o P&R promoveu a rede para
   `PRIMARY`. Um experimento com `BUFG` explícito manteve o mesmo warning e foi
   descartado. O build final passa STA no pior modelo com WNS +3,075 ns, mas a
   margem Fmax sobre 27 MHz é de aproximadamente 9,1%; o warning permanece risco
   conhecido e não foi ocultado.

## PENDENTE

- Com todo o hardware desenergizado, verificar continuidade entre o pad SD do
  INMP441 e o package pin 43, além de orientação e soldas do módulo.
- Se a continuidade SD passar, substituir o módulo INMP441/avaliar seu estágio
  de saída; qualquer retrabalho depende da decisão física do responsável.
- Depois que SD apresentar transições e samples não-zero, repetir as capturas
  DEBUG6/GAO e então executar GATES C–G e calibrar `THRESHOLD_ON/OFF` com dados
  acústicos reais.

## BLOQUEADO

A validação ponta a ponta para na camada B. DEBUG5 confirmou fisicamente SCK/WS
nos pads, mas SD segue o pull do FPGA: LOW com PULL DOWN e HIGH com NONE/UP,
sempre sem transições nos slots LEFT/RIGHT, inclusive sob tom de 1 kHz. Isso é
alta impedância contínua/circuito aberto, não saída I2S. Distinguir módulo
INMP441 defeituoso de descontinuidade no caminho SD exige teste físico com o
sistema desenergizado. Não há PASS físico de áudio nem calibração válida.

## Pinout final usado

| Sinal | Package pin / Bank | Direção | Tipo |
|---|---|---|---|
| `sys_clk` | 45 / Bank 1 | entrada FPGA | LVCMOS33, 27 MHz |
| `pi_signal` | 40 / Bank 1 | Raspberry -> FPGA | LVCMOS33 |
| `i2s_sck` | 41 / Bank 1 | FPGA -> INMP441 | LVCMOS33, drive 8 mA |
| `i2s_ws` | 42 / Bank 1 | FPGA -> INMP441 | LVCMOS33, drive 8 mA |
| `i2s_sd` | 43 / Bank 1 | INMP441 -> FPGA | LVCMOS33, pull-down |
| `led` | 10 / Bank 0 | FPGA -> LED onboard | LVCMOS18, baseline |

INMP441: VDD -> Tang 3V3, GND -> Tang GND, L/R -> GND (LEFT). Raspberry:
GPIO17/physical 11 -> Tang 40; GND/physical 9 -> Tang GND.

## Comandos exatos usados

```powershell
rg --files -uu 'C:\SAFE-FIELD'
Get-FileHash -Algorithm SHA256 -LiteralPath 'C:\SAFE-FIELD\fpga\safe_field_tang_blink\safe_field_tang_blink\src\rasp_to_tang.v','C:\SAFE-FIELD\fpga\safe_field_tang_blink\safe_field_tang_blink\src\safe_field_tang_blink.cst','C:\SAFE-FIELD\fpga\safe_field_tang_blink\safe_field_tang_blink\safe_field_tang_blink.gprj','C:\SAFE-FIELD\fpga\safe_field_tang_blink\safe_field_tang_blink\impl\pnr\safe_field_tang_blink.fs'
Copy-Item -LiteralPath 'C:\SAFE-FIELD\fpga\safe_field_tang_blink\safe_field_tang_blink' -Destination 'C:\SAFE-FIELD\fpga\tp4-audio-inmp441' -Recurse
git init -b tp4-audio-inmp441 'C:\SAFE-FIELD\fpga\tp4-audio-inmp441'
git -C 'C:\SAFE-FIELD\fpga\tp4-audio-inmp441' add --all
git -C 'C:\SAFE-FIELD\fpga\tp4-audio-inmp441' commit -m 'checkpoint: preserve physically validated GPIO17 to LED baseline'
cd 'C:\SAFE-FIELD\fpga\tp4-audio-inmp441\sim'
npm install --ignore-scripts
npm test
cd 'C:\SAFE-FIELD\fpga\tp4-audio-inmp441'
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gw_sh.exe' 'scripts\build_synthesis.tcl' 2>&1
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gw_sh.exe' 'scripts\build_all_after_pinout.tcl' 2>&1 | Tee-Object -FilePath 'evidence\build\final_build_console.log'
Get-FileHash -Algorithm SHA256 -LiteralPath 'build\full\impl\pnr\safe_field_tp4.fs'
ssh -tt -o StrictHostKeyChecking=accept-new safe-field@safe-field.local "pinctrl set 17 op dl; pinctrl get 17; date --iso-8601=seconds"
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gw_sh.exe' 'scripts\build_physical_gao.tcl'
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\Programmer\bin\programmer_cli.exe' --device GW1NSR-4C --operation_index 2 --frequency 2.5MHz --fsFile 'build\physical_gao\impl\pnr\ao_0.fs' --cable-index 1
& 'scripts\run_physical_audio_stimuli.ps1'
& 'scripts\verify_physical_evidence.ps1'
```

## Evidências principais

- `evidence/AUDIT_READONLY.md`
- `evidence/PINOUT_DOCUMENTAL_VERIFICATION.md`
- `evidence/I2S_TIMING_VERIFICATION.md`
- `evidence/FINAL_BUILD_SUMMARY.md`
- `evidence/simulation/simulation_2026-09-03T23-14-22-323Z.log`
- `evidence/build/final_build_console.log`
- `build/full/impl/pnr/safe_field_tp4.rpt.txt`
- `build/full/impl/pnr/safe_field_tp4.tr`
- `build/full/impl/pnr/safe_field_tp4.fs`
- `evidence/physical/PHYSICAL_DIAGNOSTIC_LOG.md`
- `evidence/physical/final_audit.log`
- `evidence/physical/gao_*_core0_window0.csv`
- `evidence/physical/gao_*_core1_window0.csv`
- `evidence/physical/gao_*_analysis.json`
- `build/physical_gao/impl/pnr/safe_field_tp4_physical_gao.fs`

## Referências técnicas primárias

- INMP441 datasheet rev. 1.1:
  <https://invensense.tdk.com/wp-content/uploads/2015/02/INMP441.pdf>
- Esquema oficial Sipeed Tang Nano 4K 3603:
  <https://dl.sipeed.com/fileList/TANG/Nano%204K/HDK/02_Schematic/Tang_Nano_4K_3603_Schematic_.pdf>
- Documentação/pinout Gowin UG865:
  <https://www.gowinsemi.com/en/document/main/database/400/?order=DESC&page=1&support_search=&type=category>
