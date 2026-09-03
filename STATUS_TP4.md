# STATUS TP4 — SAFE-FIELD / INMP441

Atualizado em 03/09/2026, fuso America/Sao_Paulo.

## Resumo executivo

O receptor e o processamento de áudio estão implementados, passam em simulação
auto-verificável e sintetizam para o dispositivo real `GW1NSR-LV4CQN48PC6/I5`.
O Place & Route e o novo `.fs` estão **bloqueados de forma intencional e segura**
porque nenhum arquivo local registra os três package pins aos quais o INMP441
já foi soldado. Atribuir LOCs por suposição poderia criar contenção elétrica e
violaria a regra de não inventar pinagem.

Nenhum teste físico do novo caminho de áudio foi executado ou declarado como
aprovado. A única validação física preexistente é a baseline GPIO17 -> LED
informada pelo responsável e acompanhada do arquivo local
`20260831_151428.mp4`.

## CONCLUÍDO

- Auditoria read-only inicial de `C:\SAFE-FIELD` e inventário dos 30 arquivos.
- Baseline localizada em
  `C:\SAFE-FIELD\fpga\safe_field_tang_blink\safe_field_tang_blink`.
- Baseline revalidada por SHA-256 após todo o trabalho: os quatro hashes
  essenciais permanecem idênticos aos registrados em
  `evidence\AUDIT_READONLY.md`.
- Cópia byte a byte criada em `C:\SAFE-FIELD\fpga\tp4-audio-inmp441`.
- Repositório Git local/branch `tp4-audio-inmp441`, checkpoint inicial
  `e5f232a`; `src\rasp_to_tang.v` continua sem qualquer alteração.
- Gowin Designer, Programmer, CLI e `gw_sh.exe` localizados nas versões
  V1.9.11.03 Education e V1.9.12.03. O fluxo usa V1.9.11.03 Education, igual à
  baseline.
- Pinos comprovados: clock 27 MHz = package pin 45 (projeto oficial Sipeed),
  `pi_signal` = 40 e LED = 10 (projeto e relatório P&R locais).
- Master de clock I2S: SCK = 2,700 MHz; WS = 42,1875 kHz; 32 clocks por slot e
  64 por frame estéreo. O período SCK é 370,37 ns e cada nível dura 185,185 ns.
- Receptor I2S de 24 bits, complemento de dois, MSB-first, com o atraso padrão
  de um SCK depois da troca de WS.
- `sample_data`, `sample_valid`, identificação de canal e detecção de erro de
  índice/WS implementados.
- Processamento determinístico implementado: magnitude absoluta, máximo entre
  canais por frame, média de magnitude em janela de 256 frames e FSM
  QUIET/ACTIVE com histerese (ON=50000, OFF=30000 por padrão).
- Integração preservada: a instância de `rasp_to_tang` continua no top;
  GPIO17 HIGH força o LED, GPIO17 LOW permite indicação de atividade de áudio.
- Testbench unitário/protocolo: 42 checks, 0 erros, PASS.
- Testbench ponta a ponta (clock -> modelo INMP441 -> RX -> energia/FSM -> LED):
  17 checks, 0 erros, PASS.
- Síntese Gowin final: PASS. Recursos reportados: 275 LUT, 39 ALU e 147
  registradores.
- Gate de segurança do build completo implementado e exercitado: recusou P&R e
  geração de bitstream por ausência dos três LOCs do INMP441.
- Logs de todas as simulações, tentativas/correções de síntese e bloqueio do
  build armazenados em `evidence\`.

## PENDENTE

- Confirmar fisicamente, com a placa **desenergizada**, os package pins da Tang
  Nano 4K ligados a SCK, WS e SD do INMP441, além de registrar L/R e alimentação
  3,3 V/GND.
- Inserir os três `IO_LOC` verificados em `src\safe_field_tp4.cst` e revisar os
  bancos/VCCIO antes do build.
- Executar Place & Route, analisar todos os warnings e o timing, e gerar o novo
  `build\full\impl\pnr\safe_field_tp4.fs`.
- Programar a placa somente depois da revisão de pinagem; medir SCK/WS e obter
  evidência física de voz -> LED.
- Calibrar `THRESHOLD_ON/OFF` com amostras reais do microfone/ambiente. Os
  valores atuais são funcionais em simulação, mas não foram calibrados no
  hardware.

## BLOQUEADO

Bloqueio único: os package pins físicos de `i2s_sck`, `i2s_ws` e `i2s_sd` não
existem no projeto, nos constraints, nos relatórios ou em um esquema as-built.
Ver `PINOUT_REQUIRED.md`. Sem esses dados, P&R e `.fs` do áudio não são seguros.

O gate produz exatamente:

```text
SAFETY_GATE: missing verified IO_LOC for i2s_sck, i2s_ws, i2s_sd; refusing Place & Route and bitstream generation
```

## Warnings relevantes

- Síntese final: `WARN (NL0002)` informa que a hierarquia trivial da instância
  `rasp_to_tang/gpio17_baseline` foi achatada durante otimização. A função
  combinacional que alimenta o OR do LED permanece necessária; o comportamento
  GPIO17 HIGH/LOW também foi verificado no teste ponta a ponta. O warning não
  foi ocultado e está em `evidence\build\attempt_04_synthesis_success_final.log`.
- Uma tentativa anterior teve truncamento intencional de largura na média; foi
  corrigida com slice explícito. O histórico está preservado.

## Comandos exatos usados

Auditoria e baseline:

```powershell
rg --files -uu 'C:\SAFE-FIELD'
git -C 'C:\SAFE-FIELD' status --short --branch
Get-Content -Raw -LiteralPath 'C:\SAFE-FIELD\fpga\safe_field_tang_blink\safe_field_tang_blink\safe_field_tang_blink.gprj'
Get-Content -Raw -LiteralPath 'C:\SAFE-FIELD\fpga\safe_field_tang_blink\safe_field_tang_blink\src\safe_field_tang_blink.cst'
Get-FileHash -Algorithm SHA256 -LiteralPath 'C:\SAFE-FIELD\fpga\safe_field_tang_blink\safe_field_tang_blink\src\rasp_to_tang.v','C:\SAFE-FIELD\fpga\safe_field_tang_blink\safe_field_tang_blink\src\safe_field_tang_blink.cst','C:\SAFE-FIELD\fpga\safe_field_tang_blink\safe_field_tang_blink\safe_field_tang_blink.gprj','C:\SAFE-FIELD\fpga\safe_field_tang_blink\safe_field_tang_blink\impl\pnr\safe_field_tang_blink.fs'
```

Checkpoint:

```powershell
Copy-Item -LiteralPath 'C:\SAFE-FIELD\fpga\safe_field_tang_blink\safe_field_tang_blink' -Destination 'C:\SAFE-FIELD\fpga\tp4-audio-inmp441' -Recurse
git init -b tp4-audio-inmp441 'C:\SAFE-FIELD\fpga\tp4-audio-inmp441'
git -C 'C:\SAFE-FIELD\fpga\tp4-audio-inmp441' add --all
git -C 'C:\SAFE-FIELD\fpga\tp4-audio-inmp441' commit -m 'checkpoint: preserve physically validated GPIO17 to LED baseline'
```

Simulação reproduzível:

```powershell
cd 'C:\SAFE-FIELD\fpga\tp4-audio-inmp441\sim'
npm install --ignore-scripts
npm test
```

Síntese Gowin:

```powershell
cd 'C:\SAFE-FIELD\fpga\tp4-audio-inmp441'
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gw_sh.exe' 'scripts\build_synthesis.tcl' 2>&1
```

Build completo protegido (atualmente deve falhar no gate):

```powershell
cd 'C:\SAFE-FIELD\fpga\tp4-audio-inmp441'
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gw_sh.exe' 'scripts\build_all_after_pinout.tcl' 2>&1
```

## Evidências principais

- `evidence\AUDIT_READONLY.md`
- `evidence\simulation\simulation_2026-09-03T21-36-54-888Z.log`
- `evidence\build\attempt_01_parser_error.log`
- `evidence\build\attempt_02_synthesis_warnings.log`
- `evidence\build\attempt_03_synthesis_success_with_flatten_warning.log`
- `evidence\build\attempt_04_synthesis_success_final.log`
- `evidence\build\full_build_blocked_missing_pinout.log`
- `evidence\tools\simulator_setup.log`
- `build\synthesis\impl\gwsynthesis\safe_field_tp4_syn.rpt.html`
- `build\synthesis\impl\gwsynthesis\safe_field_tp4_syn_rsc.xml`

## Referências técnicas primárias

- INMP441 datasheet, rev. 1.1:
  <https://invensense.tdk.com/wp-content/uploads/2015/02/INMP441.pdf>
- Projeto oficial Sipeed Tang Nano 4K, incluindo clock no package pin 45:
  <https://github.com/sipeed/TangNano-4K-example/blob/main/led_test/project/src/led_test.cst>
