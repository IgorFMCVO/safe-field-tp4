# SAFE-FIELD — AUDIO ACCEPTANCE REPORT

Data: 04/09/2026. Fuso: America/Sao_Paulo. Branch de reteste:
`tp4-retest-after-contact-fix`. O build final e todos os DEBUG1–7 permaneceram
inalterados. Todas as programações desta rodada usaram somente operação 2,
`SRAM Program`; nenhuma Flash foi acessada.

## Veredito

**GATE A passou após o reparo dos contatos; a cadeia completa ainda não está
aceita.** O GAO agora observa transições reais em SD, `sample_valid`, 1024/1024
samples LEFT não-zero e zero frame errors. A conclusão anterior de SD morto e
INMP441 suspeito está formalmente superada e não descreve a montagem atual.

Os testes acústicos automatizados ainda não provaram periodicidade: 500 Hz,
1 kHz e 2 kHz não apareceram nos FFTs do INMP441. Uma testemunha independente
com a matriz de microfones do Razer também não captou o tom enviado ao endpoint
Realtek. Portanto o bloqueio atual é confirmar que o estímulo realmente foi
irradiado no ambiente, e não uma falha demonstrada do I2S ou do INMP441.

> O reteste ocorreu após correção física dos contatos dos pins 41 e 43.

## Matriz de aceitação

| Camada | PASS/FAIL | Valor medido | Evidência | Arquivo |
|---|---|---|---|---|
| alimentação | PASS | 3,3 V no INMP441, informado como medido pelo operador | evidência física explicitamente fornecida pelo operador | `STATUS_TP4.md` |
| clocks | PASS | SCK=500.000 Hz; WS=7.812,5 Hz; 64 SCK/frame; 32 SCK/slot | GAO físico pós-reparo | `evidence/physical/retest_after_contact_fix/debug6_environment_01_analysis.json` |
| fiação externa SCK/WS | PASS | DEBUG5 alternância LOW/HIGH observada nos pads SCK/WS | evidência física explicitamente informada pelo operador em 04/09/2026 | `evidence/physical/PHYSICAL_DIAGNOSTIC_LOG.md` |
| SD | PASS | 8 transições na janela bruta inicial; 44 em quatro janelas de silêncio | GAO/JTAG pós-reparo | `evidence/physical/retest_after_contact_fix/GATE_A_RESULT.md` |
| decoding | PASS preliminar | 1024/1024 LEFT não-zero, signed positivos e negativos, frame errors=0 | PCM real reconstruído | `evidence/physical/retest_after_contact_fix/debug6_environment_01_core1_window0.csv` |
| samples | PASS preliminar | silêncio: 4096 samples, min=-13616, max=6912, AC RMS=3959,7 | quatro capturas GAO independentes | `evidence/physical/retest_after_contact_fix/debug6_silence_analysis_4096.json` |
| resposta acústica | BLOQUEADO | WAVs executaram, mas nem INMP441 nem microfone-testemunha captaram periodicidade | estímulo acústico não confirmado no ar | `evidence/physical/retest_after_contact_fix/razer_mic_witness_1000hz_analysis.json` |
| frequência acústica | FAIL atual | estimativas não acompanham 500/1000/2000 Hz | critério de periodicidade não atendido | `evidence/physical/retest_after_contact_fix/debug6_tone_*_analysis_4096.json` |
| magnitude/energia | PENDENTE | noise floor preliminar disponível; sem tom validado para calibração | não inventar thresholds | este relatório |
| FSM QUIET/ACTIVE | PENDENTE | não executada após o reparo | depende de estímulo acústico confirmado | este relatório |
| estabilidade 60 s/restarts | PENDENTE | não executada após o reparo | depende do GATE D | este relatório |
| integração Raspberry | PARCIAL | GPIO17 LOW confirmado; HIGH/LOW final ainda pendente | baseline preservada | `evidence/physical/retest_after_contact_fix/ssh_gpio17_attempt.log` |

O status acima é o vigente. Os resultados abaixo são preservados como histórico
anterior ao reparo e não devem ser usados para diagnosticar o hardware atual.

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

Com o sistema desenergizado, verificar continuidade do pad SD do INMP441 até o
package pin 43 e inspecionar orientação/solda do módulo. Se a continuidade for
PASS, substituir o INMP441 é a ação tecnicamente indicada. Depois, repetir
DEBUG6; somente avançar ao GATE C quando SD tiver transições e ao menos um
sample LEFT não-zero.
