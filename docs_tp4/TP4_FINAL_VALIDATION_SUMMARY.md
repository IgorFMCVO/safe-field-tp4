# SAFE-FIELD TP4 — final validation summary

Data: 04/09/2026, fuso America/Sao_Paulo. Branch:
`tp4-official-rubric-closeout`.

## Conclusão

**AUDIO PHYSICAL CHAIN = PASS. I2S DECODING = PASS. AUDIO ENERGY = PASS.
FSM FUNCTION = PASS. FSM STABILITY = RESIDUAL. GPIO17 INTEGRATION = PASS.**

**FPGA -> ARM = PASS FÍSICO. ARM -> FPGA = PASS FÍSICO. UART
BIDIRECIONAL = PASS. RUBRICA ACADÊMICA = 22/22 PASS.**

`RESIDUAL` é usado por rigor: a segunda e última iteração passou nas duas
regressões baseadas em capturas físicas e foi programada em SRAM, mas a nova
captura GAO após essa programação não foi executada. A última captura física
sincronizada foi da iteração 1 e ainda apresentou 6 transições para 2 eventos.
Não se declara PASS físico com base somente no replay.

## Validação bidirecional ARM <-> FPGA

O build acadêmico corrigido foi programado somente em SRAM. A Raspberry enviou
três comandos numéricos; a FPGA validou protocolo/CRC, processou `square16` no
DSP e respondeu pela UART Tang -> Pi já aprovada.

| Input | Expected | Actual |
|---:|---:|---:|
| 123 | 15129 | 15129 |
| -123 | 15129 | 15129 |
| 32767 | 1073676289 | 1073676289 |

- checksum errors: 0;
- sequence losses: 0;
- response errors: 0;
- evidência: `evidence/official_tp4/arm_to_fpga_physical/06_FPGA_PI_BIDIRECTIONAL.log`.

## Matriz final

| Item | Resultado |
|---|---|
| 3,3 V INMP441 | PASS — medição física informada pelo operador |
| SCK | PASS — 2,700 MHz normal; caminho externo confirmado |
| WS | PASS — 42,1875 kHz, 64 SCK/frame |
| SD | PASS — transições físicas pós-reparo |
| samples signed/non-zero | PASS — PCM LEFT real, 24 bits |
| voz x silêncio | PASS — RMS 4,99× |
| palmas | PASS — três eventos temporais |
| frame errors | PASS — 0 |
| aquisição 99,42 s | PASS |
| FSM eventos | PASS — 9/9 no registro físico; 9/9 na regressão final |
| FSM chatter | RESIDUAL físico; regressão final 100 -> 7, sem reversões <500 ms |
| GPIO17 | PASS — baseline física preservada e LOW/HIGH/LOW final restaurado |
| P&R | PASS |
| STA | PASS — setup/hold 0/0, WNS +8,156 ns |

## Causa raiz durante o desenvolvimento

Intermitência/mau contato físico nos caminhos dos pins 41 (SCK) e 43 (SD).
Após correção das conexões, o INMP441 passou a fornecer dados I2S válidos e
resposta acústica real. **O INMP441 não deve ser classificado como defeituoso.**

## Estabilização da FSM

A captura GAO de 99,42 s foi analisada antes da alteração de RTL:

- 100 transições, 51 permanências ACTIVE e 50 QUIET;
- 40 permanências menores que 500 ms;
- 52 transições a até 3.000 unidades do limiar relevante;
- dwell ACTIVE: mínimo 121 ms, mediana 1,044 s, máximo 6,056 s;
- dwell QUIET: mínimo 12 ms, mediana 212 ms, máximo 1,651 s;
- histerese preservada: `ON=12000`, `OFF=6000`, distância 6000;
- causa do chatter: cruzamentos próximos aos limiares e pausas de fala maiores
  que o release anterior de ~97 ms.

A solução mínima usa apenas persistência consecutiva e nenhum filtro/DSP novo:

- `QUIET -> ACTIVE`: `N=24` janelas consecutivas `>=12000`;
- `ACTIVE -> QUIET`: `M=82` janelas consecutivas `<=6000`;
- ataque nominal: 145,636 ms;
- release nominal: 497,588 ms;
- `minimum_active_hold`: não usado.

Regressões finais:

| Fonte física gravada | Antes | Depois | Eventos | Reversões <500 ms |
|---|---:|---:|---:|---:|
| captura 99,42 s | 100 | 7 | 9/9 preservados | 0 |
| captura sincronizada 49,71 s | 6 observadas na iteração 1 | 4 no replay da iteração 2 | 2/2 | 0 |

A captura sincronizada registrou duas vozes longas com energia média 2,36× e
1,57× as regiões adjacentes, samples não-zero e zero frame errors. A iteração
1 reconheceu 2/2 e voltou a QUIET, mas gerou um episódio extra; isso motivou a
segunda e última alteração `M=48 -> 82`.

## Build congelado

- arquivo: `C:\SAFE-FIELD\fpga\tp4-audio-inmp441\build\safe_field_tp4_audio_stable_iter2\impl\pnr\safe_field_tp4_validated.fs`
- SHA-256: `5D8F2D31EF5D0349AC0E52F13AC8A7472FCB1A23103131D13163BB8946F39181`
- dispositivo: `GW1NSR-LV4CQN48PC6/I5` (`GW1NSR-4C`)
- P&R: PASS; bitstream generation: PASS
- STA: PASS; setup/hold violados `0/0`; TNS setup/hold `0/0`;
  WNS setup `+8,156 ns`; Fmax `34,625 MHz` para requisito `27,000 MHz`
- recursos: Logic `337/4608` (8%; 296 LUT + 41 ALU), Register `184/3573`
  (6%), CLS `250/2304` (11%), I/O `6/39` (16%)
- warnings finais: 2 — `NL0002` (hierarquia trivial `rasp_to_tang` achatada;
  função preservada e simulada) e `PR1014` (rota genérica de `sys_clk_d`;
  risco conhecido coberto pelo STA positivo). Nenhum warning foi ocultado.

O `.fs` original permanece intacto em
`build\full\impl\pnr\safe_field_tp4.fs`, SHA-256
`0B04C9DF3F51B408932ED75B754F7F180001F02C50594B14CC685B4CE1BFFE8B`.

## Pinout congelado

| Sinal | Pino | Direção | Elétrica |
|---|---:|---|---|
| `sys_clk` | 45 | entrada | LVCMOS33, 27 MHz |
| `pi_signal` | 40 | entrada Raspberry -> FPGA | LVCMOS33 |
| `i2s_sck` | 41 | saída FPGA -> INMP441 | LVCMOS33 |
| `i2s_ws` | 42 | saída FPGA -> INMP441 | LVCMOS33 |
| `i2s_sd` | 43 | entrada INMP441 -> FPGA | LVCMOS33, pull-down |
| `led` | 10 | saída | LVCMOS18 |

Câmera DVP desconectada; INMP441 L/R em GND/LEFT. Nenhuma Flash foi gravada.
O bitstream final foi programado apenas em SRAM com operação 2. GPIO17 foi
comandado LOW -> HIGH -> LOW e restaurado a LOW.

## Evidências principais

- `evidence/physical/retest_after_contact_fix/fsm_stabilization/fsm_chatter_analysis.json`
- `evidence/physical/retest_after_contact_fix/fsm_stabilization/fsm_transition_details.csv`
- `evidence/physical/retest_after_contact_fix/fsm_stabilization/final_stable_cued_physical_2cycles_03_core0_window0.csv`
- `evidence/physical/retest_after_contact_fix/fsm_stabilization/cued_capture03_regression/fsm_chatter_analysis.json`
- `evidence/physical/retest_after_contact_fix/fsm_stabilization/final_stable_simulation_2026-09-04T16-07-40-847Z.log`
- `evidence/physical/retest_after_contact_fix/fsm_stabilization/safe_field_tp4_audio_stable_iter2_build.log`
- `evidence/physical/retest_after_contact_fix/fsm_stabilization/safe_field_tp4_validated_sram_program.log`
- `evidence/physical/retest_after_contact_fix/fsm_stabilization/final_gpio17_low_high_low.log`
- `build/safe_field_tp4_audio_stable_iter2/impl/pnr/safe_field_tp4_validated.rpt.txt`
- `build/safe_field_tp4_audio_stable_iter2/impl/pnr/safe_field_tp4_validated.tr`

## Auditoria do conteúdo entregue

| Categoria | Conteúdo disponível | Status |
|---|---|---|
| RTL | clock I2S, receptor 24-bit, magnitude/energia, FSM persistente, top final e GPIO17 | entregue em `src/` |
| testbenches | FSM unitária, replay 99,42 s, replay sincronizado e ponta a ponta | entregue em `tb/`; 26/26 checks finais PASS |
| constraints | pinout 40/41/42/43/45/10 e clock 27 MHz | entregue em `src/safe_field_tp4.cst` e `.sdc` |
| scripts | análise do chatter, simulação e builds Gowin reproduzíveis | entregue em `scripts/` e `sim/` |
| bitstream | `safe_field_tp4_validated.fs` independente | entregue com SHA-256 |
| Gowin | síntese, P&R, pin report, recursos, timing e logs | entregue em `build/safe_field_tp4_audio_stable_iter2/impl/` |
| GAO | configurações, CSVs, JSONs, gráficos e logs físicos | entregue em `evidence/physical/` |
| áudio | silêncio, voz, palmas, estatísticas e waveforms físicos | entregue em `evidence/physical/retest_after_contact_fix/` |
| Raspberry | GPIO17, UART bidirecional, aplicação, Assembly/NEON e binário ARM64 | entregue em `assembly_tp4/` e evidências físicas |
| reprodução | comandos de simulação, build, hash e SRAM | entregue em `README_TP4_DELIVERY.md` |
| relatórios | status, aceitação acústica e resumo final | entregue |

## Comandos essenciais executados

```powershell
python scripts\analyze_fsm_chatter.py evidence\physical\retest_after_contact_fix\stable_cued_fsm_10cycles_04_valid_core0_window0.csv --output-dir evidence\physical\retest_after_contact_fix\fsm_stabilization
node sim\run-final-stable.mjs
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gw_sh.exe' scripts\build_safe_field_tp4_audio_stable_cued_iter2.tcl
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gw_sh.exe' scripts\build_safe_field_tp4_audio_stable_iter2.tcl
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\Programmer\bin\programmer_cli.exe' --device GW1NSR-4C --operation_index 2 --frequency 2.5MHz --fsFile build\safe_field_tp4_audio_stable_iter2\impl\pnr\safe_field_tp4_validated.fs --cable-index 1
Get-FileHash -Algorithm SHA256 build\safe_field_tp4_audio_stable_iter2\impl\pnr\safe_field_tp4_validated.fs
```

## Fechamento da entrega acadêmica

- rubrica: 22/22 PASS;
- PDF definitivo: gerado após o PASS ARM -> FPGA;
- ZIP definitivo: regenerado e verificado;
- vídeo: https://youtu.be/1Ancm5QdG2E;
- única providência externa restante: inserir o link final do Google Drive no
  campo `PENDENTE_LINK_FINAL` antes da submissão na plataforma oficial.
