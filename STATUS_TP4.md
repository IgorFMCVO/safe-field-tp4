# STATUS TP4 — SAFE-FIELD / INMP441

Atualizado em 03/09/2026, fuso America/Sao_Paulo.

## Resumo executivo

O checkpoint `tp4-audio-inmp441` contém receptor I2S de 24 bits, geração de
SCK/WS, `sample_valid`, magnitude/média, FSM com histerese e integração com o
caminho GPIO17 -> LED preexistente. Simulação, síntese, Place & Route, STA e
geração do `.fs` passaram. A Tang Nano 4K **não foi programada**.

Bitstream revisado:
`C:\SAFE-FIELD\fpga\tp4-audio-inmp441\build\full\impl\pnr\safe_field_tp4.fs`

SHA-256:
`0B04C9DF3F51B408932ED75B754F7F180001F02C50594B14CC685B4CE1BFFE8B`

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

- Programar a Tang somente após a autorização/revisão física solicitada.
- Com a placa desenergizada, confirmar que não há módulo/driver no conector DVP
  compartilhado com 41/42/43 e verificar se o módulo INMP441 possui o pull-down
  de 100 kOhm recomendado em SD.
- Após energizar, medir SCK e WS; verificar 2,700 MHz e 42,1875 kHz, aguardar
  pelo menos ~100 ms de startup do INMP441 e capturar SD/amostras/LED como
  evidência física.
- Calibrar `THRESHOLD_ON/OFF` com ruído ambiente e voz reais. Os valores atuais
  passaram em simulação, mas ainda não têm calibração acústica física.

## BLOQUEADO

A validação física do novo caminho de áudio está bloqueada deliberadamente pela
ordem **NÃO programar a Tang ainda**. Não há afirmação de PASS físico para áudio.
A única evidência física existente continua sendo a baseline GPIO17 LOW/HIGH
informada e previamente validada pelo responsável.

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

## Referências técnicas primárias

- INMP441 datasheet rev. 1.1:
  <https://invensense.tdk.com/wp-content/uploads/2015/02/INMP441.pdf>
- Esquema oficial Sipeed Tang Nano 4K 3603:
  <https://dl.sipeed.com/fileList/TANG/Nano%204K/HDK/02_Schematic/Tang_Nano_4K_3603_Schematic_.pdf>
- Documentação/pinout Gowin UG865:
  <https://www.gowinsemi.com/en/document/main/database/400/?order=DESC&page=1&support_search=&type=category>
