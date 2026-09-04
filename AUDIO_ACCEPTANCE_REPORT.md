# SAFE-FIELD — AUDIO ACCEPTANCE REPORT

Data: 04/09/2026. Fuso: America/Sao_Paulo. Branch de diagnóstico:
`tp4-audio-acceptance`. O build final e todos os DEBUG1–5 permaneceram
inalterados. Todas as programações desta rodada usaram somente operação 2,
`SRAM Program`; nenhuma Flash foi acessada.

## Veredito

**A cadeia de áudio NÃO está aceita e o INMP441 NÃO deve ser declarado
operacional.** O GATE A falhou porque SD não apresentou transições nem sample
LEFT diferente de zero. O GATE B demonstrou que SD segue o pull interno do
FPGA e permanece em alta impedância durante ambos os slots, inclusive durante
tom de 1 kHz. Conforme o critério solicitado, o módulo INMP441 — incluindo seu
estágio/pad de saída SD — é o principal suspeito físico.

Ainda existe uma alternativa física que software não distingue: circuito
aberto entre o pad SD do módulo e o package pin 43. SCK e WS foram excluídos
dessa hipótese porque o operador confirmou explicitamente DEBUG5 LOW/HIGH nos
pads do próprio INMP441. Resolver a distinção INMP441 versus continuidade de SD
exigiria medição/inspeção física, proibida nesta execução.

## Matriz de aceitação

| Camada | PASS/FAIL | Valor medido | Evidência | Arquivo |
|---|---|---|---|---|
| alimentação | PASS | 3,3 V no INMP441, informado como medido pelo operador | evidência física explicitamente fornecida pelo operador | `STATUS_TP4.md` |
| clocks | PASS | SCK=500.000 Hz; WS=7.812,5 Hz; 64 SCK/frame; 32 SCK/slot | GAO físico, modal de 54 sys_clks/SCK e 1728 sys_clks/meio-frame | `evidence/physical/debug7_sd_slot_diagnostic/pull_none_slot_analysis.json` |
| fiação externa SCK/WS | PASS | DEBUG5 alternância LOW/HIGH observada nos pads SCK/WS | evidência física explicitamente informada pelo operador em 04/09/2026 | `evidence/physical/PHYSICAL_DIAGNOSTIC_LOG.md` |
| SD | FAIL | DOWN: 0/1025 HIGH; NONE: 4096/4096 HIGH; UP: 4096/4096 HIGH; zero transições estáveis | SD muda com o pull configurado e não com WS/áudio | `evidence/physical/debug7_sd_slot_diagnostic/sd_bias_comparison.png` |
| decoding | FAIL | 512×0 com pull-down; 512×-1 com NONE/UP; frame errors=0 | receptor avança corretamente, mas reconstrói somente o nível de bias | `evidence/physical/debug6_low_rate_i2s/gate_a_initial_analysis.json`; `evidence/physical/debug7_sd_slot_diagnostic/pull_up_slot_analysis.json` |
| samples | FAIL | nenhum sample físico atribuível ao microfone | 0/512 não-zero no GATE A; 512 valores constantes -1 no pull-up não são áudio | mesmos JSONs acima |
| resposta acústica | FAIL | tom 1 kHz: SD HIGH 4096/4096, 0 transições, 512×-1 | captura GAO simultânea a WAV 1 kHz, amplitude digital 12% | `evidence/physical/debug7_sd_slot_diagnostic/pull_up_tone_1000hz_slot_analysis.json` |
| frequência acústica | FAIL | não estimável | não existe waveform real; estimar frequência de bias constante seria fictício | `evidence/physical/debug7_sd_slot_diagnostic/pull_up_tone_1000hz_core1_window0.csv` |
| magnitude/energia | FAIL | não calibrável | nenhuma amostra real; thresholds não foram alterados | `evidence/physical/debug6_low_rate_i2s/gate_a_initial_core1_window0.csv` |
| FSM QUIET/ACTIVE | FAIL | não executada fisicamente | bloqueada pelo GATE A/B, evitando falso resultado com bias | este relatório |
| estabilidade 60 s/restarts | FAIL | não executada | GATE F depende de samples reais e foi bloqueado pelo GATE B | este relatório |
| integração Raspberry | FAIL | GPIO17 LOW confirmado; aceitação ponta a ponta não executada | override baseline preservado, mas GATE G depende de áudio válido | `evidence/physical/debug6_low_rate_i2s/gpio17_low.log` |

`FAIL` nas etapas C–G significa “critério de aceitação não atingido”, não falha
demonstrada da lógica correspondente. Elas foram deliberadamente interrompidas
porque o plano proíbe avançar para processamento quando SD não transmite.

## GATE A — DEBUG6_LOW_RATE_I2S

### Build

- Simulação: PASS, 14 checks, 0 erros.
- Síntese/P&R: PASS.
- STA: PASS, 2.918 paths, 0 endpoints setup/hold violados, TNS 0/0;
  Fmax `sys_clk` 83,677 MHz para requisito de 27 MHz.
- Recursos: Logic 1116/4608 (25%), registros 1117/3573 (32%), CLS 942/2304
  (41%) e I/O 10/39 (26%).
- Warnings: 55 linhas — 52× `PA1001` em nets/saídas não usadas do IP GAO e
  carry superior do receptor; 2× `TA1117` na relação entre clock gerado WS e
  sys_clk do core GAO; 1× `PR1014` conhecido em `sys_clk_d`. Todos foram
  preservados. P&R e os três domínios reportam TNS=0 e zero violações.

Bitstream SRAM/GAO:
`C:\SAFE-FIELD\fpga\tp4-audio-inmp441\build\debug6_low_rate_i2s\impl\pnr\ao_0.fs`

SHA-256:
`D930622FF7C1407D33C0EA0B2324B7DFB8892E6FDE08B98F2A4D40F603876105`

### Captura física

- 512 samples LEFT capturados.
- SCK físico: 500.000 Hz, período de 54 clocks de 27 MHz.
- `sample_valid_toggle`: 511 transições nas 512 linhas.
- frame errors: 0.
- raw SD: 0 transições, LOW constante com pull-down.
- samples: 512 zeros; min=0; max=0; média=0; média absoluta=0; RMS=0.

Resultado GATE A: **FAIL**, pois não houve transição SD nem sample LEFT
diferente de zero. GATES C–G não foram iniciados.

## GATE B — DEBUG7_SD_SLOT_DIAGNOSTIC

As duas variantes reutilizam exatamente o clock/receptor do DEBUG6. O core GAO
profundo captura 4096 sys_clks, mais que um frame completo, e 512 samples LEFT.

| Variante | SD por slot WS=0/LEFT | SD por slot WS=1/RIGHT | Samples | Interpretação |
|---|---|---|---|---|
| PULL NONE | 1728/1728 HIGH, 0 transições | 2368/2368 HIGH, 0 transições | 512×-1 | HIGH constante, sem drive LEFT detectável |
| PULL UP | 2368/2368 HIGH, 0 transições | 1728/1728 HIGH, 0 transições | 512×-1 | alta impedância ou circuito aberto nos dois slots |
| PULL UP + tom 1 kHz | 1728/1728 HIGH, 0 transições | 2368/2368 HIGH, 0 transições | 512×-1 | estímulo acústico não altera SD |

Em todas as capturas: SCK=500.000 Hz, WS=7.812,5 Hz, 64 SCK/frame e frame
errors=0. O contador SD registra apenas a transição inicial de reset/bias e
permanece em 1; não cresce durante os frames.

Build NONE:
`C:\SAFE-FIELD\fpga\tp4-audio-inmp441\build\debug7_sd_slot_diagnostic_none\impl\pnr\ao_0.fs`

SHA-256 NONE:
`3A6FD06F8B4515DEFF827F42EBC83D1FC56033DE817D147F567D3919C278AE7E`

Build UP, exclusivamente diagnóstico:
`C:\SAFE-FIELD\fpga\tp4-audio-inmp441\build\debug7_sd_slot_diagnostic_up\impl\pnr\ao_0.fs`

SHA-256 UP:
`4C5ED5A0DE02ABCA1C6E2AF26039A469EF4F7E32958A018E434A798A04EE3DAC`

Ambos: simulação, síntese, P&R e STA PASS; 0 violações setup/hold. Recursos:
Logic 1130/4608 (25%), registros 1137/3573 (32%), CLS 973/2304 (43%), I/O
10/39 (26%), BSRAM 7/10 (70%). Cada build emitiu 153 warnings: 150× `PA1001`
do gerador GAO/memórias parcialmente usadas, 2× `TA1117` e 1× `PR1014`;
nenhum foi ocultado. Pinout P&R confirmou SD como entrada e pull correto em
cada variante.

Resultado GATE B: **FAIL para atividade do INMP441; PASS para o diagnóstico de
alta impedância contínua**. A variante UP não é build final. Após as capturas,
o FPGA foi restaurado por SRAM ao DEBUG6 com PULL DOWN.

## GATES C–G

- GATE C: não executado; não existem 4096 samples reais para estatística.
- GATE D: não executado; não existe waveform acústico para frequência/gráficos.
- GATE E: não executado; calibrar thresholds a partir de zeros/-1 seria inválido.
- GATE F: não executado; estabilidade de parser sem fonte SD não aceita áudio.
- GATE G: não executado ponta a ponta; GPIO17 e seu override foram preservados.

Nenhum threshold calibrado ou build “final físico” foi criado.

## Evidências e comandos

Evidências principais:

- `evidence/physical/debug6_low_rate_i2s/gate_a_initial_core0_window0.csv`
- `evidence/physical/debug6_low_rate_i2s/gate_a_initial_core1_window0.csv`
- `evidence/physical/debug6_low_rate_i2s/gate_a_initial_analysis.json`
- `evidence/physical/debug7_sd_slot_diagnostic/pull_none_core0_window0.csv`
- `evidence/physical/debug7_sd_slot_diagnostic/pull_none_core1_window0.csv`
- `evidence/physical/debug7_sd_slot_diagnostic/pull_none_slot_analysis.json`
- `evidence/physical/debug7_sd_slot_diagnostic/pull_up_core0_window0.csv`
- `evidence/physical/debug7_sd_slot_diagnostic/pull_up_core1_window0.csv`
- `evidence/physical/debug7_sd_slot_diagnostic/pull_up_slot_analysis.json`
- `evidence/physical/debug7_sd_slot_diagnostic/pull_up_tone_1000hz_core0_window0.csv`
- `evidence/physical/debug7_sd_slot_diagnostic/pull_up_tone_1000hz_core1_window0.csv`
- `evidence/physical/debug7_sd_slot_diagnostic/pull_up_tone_1000hz_slot_analysis.json`
- `evidence/physical/debug7_sd_slot_diagnostic/sd_bias_comparison.png`
- logs de build, programação SRAM e GAO nos mesmos diretórios.

Comandos essenciais executados:

```powershell
node 'sim\run-debug6.mjs'
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gw_sh.exe' 'scripts\build_debug6_low_rate_i2s.tcl'
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\Programmer\bin\programmer_cli.exe' --device GW1NSR-4C --operation_index 2 --frequency 2.5MHz --fsFile 'build\debug6_low_rate_i2s\impl\pnr\ao_0.fs' --cable-index 1
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gao_sh.exe' -gao 'src\debug6_low_rate_i2s.rao' -out 'evidence\physical\debug6_low_rate_i2s\gate_a_initial' -device GW1NSR-4C -cable FT2CH -location 0
python 'scripts\analyze_gao_capture.py' 'evidence\physical\debug6_low_rate_i2s\gate_a_initial'
node 'sim\run-debug7.mjs'
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gw_sh.exe' 'scripts\build_debug7_sd_slot_none.tcl'
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gw_sh.exe' 'scripts\build_debug7_sd_slot_up.tcl'
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\Programmer\bin\programmer_cli.exe' --device GW1NSR-4C --operation_index 2 --frequency 2.5MHz --fsFile '<DEBUG7>\impl\pnr\ao_0.fs' --cable-index 1
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gao_sh.exe' -gao '<DEBUG7>\debug7_sd_slot_diagnostic.rao' -out '<capture-prefix>' -device GW1NSR-4C -cable FT2CH -location 0
python 'scripts\analyze_sd_slots.py' '<capture-prefix>' '<NONE|UP>'
python 'scripts\plot_sd_slot_diagnostic.py'
```

Senha SSH foi fornecida interativamente e não foi persistida em arquivo.

## Próxima ação física indispensável

Com o sistema desenergizado, verificar continuidade do pad SD do INMP441 até o
package pin 43 e inspecionar orientação/solda do módulo. Se a continuidade for
PASS, substituir o INMP441 é a ação tecnicamente indicada. Depois, repetir
DEBUG6; somente avançar ao GATE C quando SD tiver transições e ao menos um
sample LEFT não-zero.
