# STATUS — bitstreams diagnósticos INMP441

Data: 03/09/2026. Branch: `tp4-audio-diagnostics`.
Base imutável: commit `a199a88` da branch `tp4-audio-inmp441`.

O `.fs` TP4 original continua com SHA-256
`0B04C9DF3F51B408932ED75B754F7F180001F02C50594B14CC685B4CE1BFFE8B`.
Nenhum build diagnóstico escreve em `build/full` e nenhuma placa foi programada
automaticamente.

## Matriz final

| Build | P&R | STA | WNS setup | Fmax | Recursos Logic/Reg/CLS | SHA-256 |
|---|---|---|---:|---:|---|---|
| DEBUG 1 | PASS | PASS, 0/0 violações | +30,060 ns | 143,325 MHz | 72/52/45 | `F1011244D4CB641A7526E031E2AC1EB74D4FE4DC12D23CF59E525B5F28BC3EBF` |
| DEBUG 2 | PASS | PASS, 0/0 violações | +25,254 ns | 84,869 MHz | 192/110/113 | `372114B1DED654BDE00DE151D9F38EA06A8E66E8FB60C9524E1F16C772DEB475` |
| DEBUG 3 | PASS | PASS, 0/0 violações | +25,490 ns | 86,602 MHz | 104/106/87 | `D06F286F0551E4E0AEECF88E2E97021B1B4C2E08C7D90E5B871C962F3E4694A4` |
| DEBUG 4 | PASS | PASS, 0/0 violações | +7,150 ns | 33,459 MHz | 312/147/208 | `AD16B4EDDCD476633E0FDF755482B63B5AF6174A98C69F762DD75BB30D301487` |

`Logic/Reg/CLS` são contagens usadas. Todos os builds exigem 27,000 MHz.

## Artefatos e comportamento esperado

### DEBUG 1 — I2S_INTERNAL_ACTIVITY

`C:\SAFE-FIELD\fpga\tp4-audio-inmp441\build\debug1_i2s_internal_activity\impl\pnr\debug1_i2s_internal_activity.fs`

Com GPIO17 LOW, o LED pisca a aproximadamente 1 Hz, contando exclusivamente
frames completos indicados por `sample_valid` do slot RIGHT. Isso prova avanço
do gerador SCK/WS e da máquina de recepção, mas não prova atividade de SD.

### DEBUG 2 — SD_TRANSITION_DETECT

`C:\SAFE-FIELD\fpga\tp4-audio-inmp441\build\debug2_sd_transition_detect\impl\pnr\debug2_sd_transition_detect.fs`

Depois de 2^18 bordas SCK de startup (~97,1 ms), oito ou mais transições raw SD
em uma janela de 2^20 ciclos (~38,8 ms) mantêm o LED ligado por pelo menos
500 ms; parsing e thresholds acústicos não participam.

### DEBUG 3 — NONZERO_SAMPLE

`C:\SAFE-FIELD\fpga\tp4-audio-inmp441\build\debug3_nonzero_sample\impl\pnr\debug3_nonzero_sample.fs`

Qualquer sample LEFT reconstruído com magnitude estritamente maior que 512
mantém o LED ligado por pelo menos 500 ms. Contadores internos de samples zero e
não-zero foram verificados em simulação (`zero=2`, `nonzero=1`).

### DEBUG 4 — LOW_THRESHOLD_AUDIO

`C:\SAFE-FIELD\fpga\tp4-audio-inmp441\build\debug4_low_threshold_audio\impl\pnr\debug4_low_threshold_audio.fs`

O pipeline final completo usa temporariamente ON=2000 e OFF=1000; com GPIO17
LOW, a média acima/abaixo desses limites aciona/desaciona o LED.

## Simulação

Suíte final: PASS. Baseline/protocolo 42/42, ponta a ponta 17/17, DEBUG 1 7/7,
DEBUG 2 7/7, DEBUG 3 10/10 e DEBUG 4 5/5, total 88 checks e 0 erros.

Log: `evidence/simulation/simulation_2026-09-04T01-01-06-542Z.log`.

## Pinout comum confirmado pós-P&R

| Sinal | Package pin / banco | Direção/tipo |
|---|---|---|
| `sys_clk` | 45 / Bank 1 | entrada LVCMOS33 |
| `pi_signal` | 40 / Bank 1 | entrada LVCMOS33 |
| `i2s_sck` | 41 / Bank 1 | saída LVCMOS33, 8 mA |
| `i2s_ws` | 42 / Bank 1 | saída LVCMOS33, 8 mA |
| `i2s_sd` | 43 / Bank 1 | entrada LVCMOS33, pull-down |
| `led` | 10 / Bank 0 | saída LVCMOS18, 8 mA |

A câmera/DVP deve permanecer fisicamente desconectada e GPIO17 deve ficar LOW
para que seu override não masque o LED de diagnóstico.

## Warnings analisados

- Todos os quatro: `PR1014` no ingresso de `sys_clk_d` pelo pino 45
  `LPLL_T_in`; a rede resultante é `PRIMARY` e todos passam STA com ampla margem.
- DEBUG 1: `CV0016`, `i2s_sd` não usado. É esperado: o LED mede frames internos,
  não o valor de SD. O relatório P&R ainda confirma o port no pino 43.
- DEBUG 4: `NL0002`, achatamento da hierarquia combinacional
  `rasp_to_tang`; o GPIO17 continua no cone do LED.

## Árvore de uso físico

1. Programar DEBUG 1 e manter GPIO17 LOW. Se não piscar: clock/build/interno.
2. Se DEBUG 1 piscar, programar DEBUG 2. Se não acionar: SD/microfone/ligação.
3. Se DEBUG 2 acionar, programar DEBUG 3. Se não acionar: alinhamento/parsing.
4. Se DEBUG 3 acionar, programar DEBUG 4. Se não acionar: média/FSM/histerese.
5. Se DEBUG 3 e DEBUG 4 acionarem: provável calibração dos thresholds finais.

Nenhum desses resultados físicos foi assumido ou registrado como PASS.

## Comandos reproduzíveis

```powershell
cd 'C:\SAFE-FIELD\fpga\tp4-audio-inmp441\sim'
npm test
cd 'C:\SAFE-FIELD\fpga\tp4-audio-inmp441'
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gw_sh.exe' 'scripts\build_debug1_i2s_internal_activity.tcl'
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gw_sh.exe' 'scripts\build_debug2_sd_transition_detect.tcl'
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gw_sh.exe' 'scripts\build_debug3_nonzero_sample.tcl'
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gw_sh.exe' 'scripts\build_debug4_low_threshold_audio.tcl'
& 'C:\SAFE-FIELD\fpga\tp4-audio-inmp441\scripts\verify_diagnostics.ps1'
```
