# SAFE-FIELD — AUDIO ACCEPTANCE REPORT

Data: 04/09/2026. Fuso: America/Sao_Paulo. Branch de reteste:
`tp4-retest-after-contact-fix`. O build final e todos os DEBUG1–7 permaneceram
inalterados. Todas as programações desta rodada usaram somente operação 2,
`SRAM Program`; nenhuma Flash foi acessada.

## Adendo final de estabilidade — prevalece sobre o histórico abaixo

- Cadeia acústica física: **PASS**.
- FSM funcional: **PASS**.
- FSM estabilidade: **RESIDUAL físico / PASS nas regressões gravadas**.
- Iteração final: `ON=12000`, `OFF=6000`, `N=24`, `M=82`, ataque nominal
  145,636 ms, release nominal 497,588 ms, sem `minimum_active_hold`.
- Captura física longa: `100 -> 7` transições no replay, 9/9 eventos, zero
  reversões <500 ms.
- Captura física sincronizada de 49,71 s: duas vozes com razões de energia
  2,36× e 1,57×, 2/2 detectadas, frame errors=0; replay final produziu quatro
  transições e QUIET entre eventos. A iteração 1 em hardware havia produzido
  seis transições, por isso não é registrada como estabilidade PASS.
- Bitstream final: `build/safe_field_tp4_audio_stable_iter2/impl/pnr/safe_field_tp4_validated.fs`;
  SHA-256 `5D8F2D31EF5D0349AC0E52F13AC8A7472FCB1A23103131D13163BB8946F39181`.
- P&R/STA: PASS, setup/hold 0/0, WNS +8,156 ns, Fmax 34,625 MHz.
- GPIO17: PASS; LOW/HIGH/LOW final e restauração a LOW, preservando a baseline.

O resultado permanece `RESIDUAL`, não `PASS`, porque a iteração 2 não teve uma
nova captura GAO depois da programação SRAM. Consulte
`TP4_FINAL_VALIDATION_SUMMARY.md` para a matriz final e a lista de entrega.

## Veredito

**A captação acústica física passou em baixa velocidade e na taxa normal; a
aceitação completa até o GATE G ainda está em andamento.** O GAO observou voz
humana com RMS 4,99 vezes o silêncio e três palmas distintas nas duas taxas,
sempre sem frame errors. O pipeline normal também entrou em ACTIVE com os
limiares originais, mas por apenas aproximadamente 0,56 s, confirmando que
50000/30000 é excessivamente conservador para voz normal.

Os antigos testes de tons do Razer permanecem inválidos como ensaio acústico:
não houve confirmação de emissão física e o microfone-testemunha também não os
captou. Eles não contam como FAIL do INMP441 nem como teste de frequência.

> Após reparo dos contatos dos pins 41 e 43, SD voltou a transmitir dados e o diagnóstico anterior de falha do INMP441 foi invalidado.

## Matriz de aceitação

| Camada | PASS/FAIL | Valor medido | Evidência | Arquivo |
|---|---|---|---|---|
| alimentação | PASS | 3,3 V no INMP441, informado como medido pelo operador | evidência física explicitamente fornecida pelo operador | `STATUS_TP4.md` |
| clocks | PASS | SCK=500.000 Hz; WS=7.812,5 Hz; 64 SCK/frame; 32 SCK/slot | GAO físico pós-reparo | `evidence/physical/retest_after_contact_fix/debug6_environment_01_analysis.json` |
| fiação externa SCK/WS | PASS | DEBUG5 alternância LOW/HIGH observada nos pads SCK/WS | evidência física explicitamente informada pelo operador em 04/09/2026 | `evidence/physical/PHYSICAL_DIAGNOSTIC_LOG.md` |
| SD | PASS | 8 transições na janela bruta inicial; 44 em quatro janelas de silêncio | GAO/JTAG pós-reparo | `evidence/physical/retest_after_contact_fix/GATE_A_RESULT.md` |
| decoding | PASS | 8192 samples contínuos na taxa normal, signed positivos e negativos, frame errors=0 | PCM real reconstruído | `evidence/physical/retest_after_contact_fix/normal_voice_real_01_continuous_samples.csv` |
| samples | PASS | silêncio normal RMS=4010,69; voz RMS=20023,63; pico de voz=84992 | capturas GAO físicas independentes | `evidence/physical/retest_after_contact_fix/normal_voice_vs_silence_comparison.json` |
| resposta acústica | PASS | voz/silêncio RMS=4,993 e média absoluta=4,373; três palmas distintas em baixa e normal | voz humana e palmas informadas pelo operador e medidas no FPGA | `evidence/physical/retest_after_contact_fix/normal_voice_vs_silence_comparison.json` |
| frequência acústica | PENDENTE | tons anteriores não são ensaios válidos porque a emissão no ar não foi confirmada | não classificar ausência espectral como falha do INMP441 | `evidence/physical/retest_after_contact_fix/razer_mic_witness_1000hz_analysis.json` |
| magnitude/energia | PASS de observação | energia física por 256 frames: 8192 pontos, min=736, mediana=4096, máx=62112; overflow=0 | GAO direto no detector | `evidence/physical/retest_after_contact_fix/energy_calibration_5cycles_01_energy_analysis.json` |
| FSM QUIET/ACTIVE | PARCIAL | ON=16000/OFF=8000 obteve 8/10; variante temporal ON=12000/OFF=6000 observou ACTIVE e retorno a QUIET em 9/9 janelas completas | fala confirmada pelo operador, com ressalva de possível ciclo pulado; estabilidade ainda FAIL | `evidence/physical/retest_after_contact_fix/OPERATOR_CONFIRMATION_10CYCLES.md` |
| estabilidade 60 s/restarts | FAIL da FSM / PASS da aquisição | aquisição contínua 99,42 s e frame errors=0; FSM temporal ainda apresentou 100 transições | GAO profundo real | `evidence/physical/retest_after_contact_fix/stable_cued_fsm_10cycles_04_valid_core0_window0.csv` |
| integração Raspberry | PASS de instrumentação | GPIO17 HIGH acende e LOW apaga o LED, alternou durante aquisição sem frame error | nível físico confirmado pelo operador e GAO simultâneo | `evidence/physical/retest_after_contact_fix/stable_cued_fsm_10cycles_04_valid_core0_window0.csv` |

O status acima é o vigente. Os resultados abaixo são preservados como histórico
anterior ao reparo e não devem ser usados para diagnosticar o hardware atual.

## Captação acústica real pós-reparo

### DEBUG6, 500 kHz / 7,8125 kHz

- Silêncio contínuo: 8192 samples LEFT, min=-16882, max=8542,
  média absoluta=4681,39, RMS=5587,06, desvio padrão=5107,71, 5411 valores
  distintos, zero frame errors.
- Voz humana: RMS=14216,89 contra 4557,35 antes da fala, razão=3,120;
  pico=86016 e zero frame errors. PASS físico.
- Três palmas: picos em 0,0215 s, 1,0988 s e 1,9651 s; intervalos de 1,077 s
  e 0,866 s, zero frame errors. PASS físico.
- Distância: a captura próxima teve bloco RMS máximo 12058,7 contra 10791,9
  a aproximadamente 1 m. Tendência próxima > distante confirmada, com margem
  modesta e sem calibração SPL.
- Repetibilidade: cinco pares voz/silêncio PASS, razões RMS 2,124; 2,587;
  2,671; 2,777 e 2,324.

### Taxa normal, 2,700 MHz / 42,1875 kHz

- Silêncio: RMS=4010,69, média absoluta=3267,63 e pico=16384.
- Voz: RMS=20023,63, média absoluta=14288, pico=84992; razões sobre silêncio
  4,993 e 4,373. Zero frame errors. `PHYSICAL ACOUSTIC CAPTURE = PASS`.
- Palmas: três eventos em 0,666 s, 1,810 s e 2,810 s, com intervalos de
  1,144 s e 1,000 s. Zero frame errors. PASS físico.
- A FSM original chegou a ACTIVE, mas somente em 368 pontos GAO decimados
  (~0,558 s). Isso explica a indicação visual esporádica com voz.

### Calibração

A observação direta de 8192 médias reais de 256 frames mostrou min=736,
mediana=4096, p90=11456, p95=15056, máximo=62112 e nenhum overflow/erro de
frame. Combinando-a com a referência física de silêncio, o candidato inicial é
`THRESHOLD_ON=16000` e `THRESHOLD_OFF=8000`. O ON fica acima do máximo de
janela de silêncio aproximado (14848); o OFF fica acima da vizinhança p95
(7168) e preserva histerese de 8000.

Uma tentativa automática marcou cinco janelas por GPIO17, mas o operador
confirmou que não falou durante elas. O arquivo foi preservado e classificado
`INCONCLUSIVE`; não é FAIL do microfone nem do threshold. A variante calibrada
ON=16000/OFF=8000 passou simulação/P&R/STA, mas obteve 8/10 pares e 130
comutações em 99,42 s. A variante temporal separada ON=12000/OFF=6000,
ataque de duas janelas, retenção mínima de 82 janelas (~498 ms) e liberação
após 16 janelas passou 11/11 checks de simulação, P&R e STA. O GAO observou
ACTIVE e retorno a QUIET em todas as nove janelas completas exportadas, sem
frame error, mas ainda com 100 transições em 99,42 s. O operador confirmou a
fala, ressalvando que pode ter pulado um ciclo. Resultado: detecção 9/9 PASS;
estabilidade FAIL. Não se alega 10/10.

Bitstream temporal em SRAM:
`C:\SAFE-FIELD\fpga\tp4-audio-inmp441\build\stable_cued_capture\impl\pnr\ao_0.fs`.
SHA-256: `99E43D60FBCE01CFBC6270624C4741AAB9DF30D69DE4D34B6031CEC2416639E7`.
Recursos: Logic 871/4608 (19%), Register 573/3573 (17%), CLS 640/2304
(28%), BSRAM 10/10. STA: zero violações setup/hold, Fmax sys_clk=31,761 MHz
para 27 MHz. Warnings preservados: 331 (1 NL0002, 327 PA1001 do GAO/BSRAM e
carries não consumidos, 2 TA1117 entre domínios observacionais e 1 PR1014 do
clock de entrada já conhecido).

Depois da captura, foi gerado e programado somente em SRAM o candidato
funcional equivalente, com LED=`GPIO17 OR sound_active`, mantendo o build TP4
original intacto. Simulação 10/10 PASS, P&R PASS, STA PASS com zero violações,
Fmax=29,638 MHz para 27 MHz, recursos Logic 358/4608 (8%), Register 160/3573
(5%) e CLS 244/2304 (11%). Warnings: 2 (NL0002 e PR1014 já analisados).
Arquivo:
`C:\SAFE-FIELD\fpga\tp4-audio-inmp441\build\stable_audio_candidate\impl\pnr\safe_field_stable_audio.fs`;
SHA-256 `D5F94C664BB1882437CA3BD235A70913F00E1419C17C7943A33CEA64D80E7858`.

## Reteste DEBUG6 pós-correção de contato

- Branch/checkpoint: `tp4-retest-after-contact-fix`, início `6fbe4f5`.
- Simulação: PASS, 14/14 checks.
- Síntese/P&R: PASS; STA PASS, 3194 paths, zero violações setup/hold.
- Recursos GAO profundo: Logic 1173/4608 (26%), Register 1143/3573 (32%),
  CLS 992/2304 (44%), I/O 10/39 (26%), BSRAM 10/10 (100%).
- Warnings preservados: 262 — 259× PA1001 do GAO/memórias/carries não
  consumidos, 2× TA1117 entre domínios assíncronos do GAO e 1× PR1014 na rota
  genérica conhecida de `sys_clk_d`.
- Bitstream programado somente em SRAM:
  `C:\SAFE-FIELD\fpga\tp4-audio-inmp441\build\debug6_retest_after_contact_fix\impl\pnr\ao_0.fs`.
- SHA-256: `7C1F24C7FE1B1142245AE53973B49C8A32807C6BFA77C27496D17C4CC3EA0B6F`.
- Primeira captura: SCK 500 kHz, WS 7,8125 kHz, 1024 samples não-zero,
  min=-9736, max=3078, RMS=5276,15, 8 transições SD e zero frame errors.
- Silêncio agregado: 4096 samples; 1 zero/4095 não-zero; min=-13616;
  max=6912; mean=-3043,40; mean abs=3987,71; AC RMS=3959,67; pico=13616;
  clipping=0; frame errors=0.

## Registro histórico anterior à correção — não vigente

### GATE A — DEBUG6_LOW_RATE_I2S antes do reparo

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

A aquisição acústica já é PASS e a confirmação do operador foi registrada. O
trabalho restante é estabilizar a classificação QUIET/ACTIVE e executar os
três restarts SRAM; nenhuma intervenção elétrica é necessária.
