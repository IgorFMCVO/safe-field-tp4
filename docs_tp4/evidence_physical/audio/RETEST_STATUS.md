# SAFE-FIELD — reteste pós-correção dos contatos

Data local: 04/09/2026. Branch: `tp4-retest-after-contact-fix`.

> O reteste ocorreu após correção física dos contatos dos pins 41 e 43.

## Resultado atual

| Gate | Estado | Valor/evidência |
|---|---|---|
| JTAG | PASS | GW1NSR-4C, IDCODE 0x0100981B |
| GPIO17 | PASS | output LOW às 09:30:43 -03:00 |
| DEBUG6 simulação | PASS | 14/14 checks |
| DEBUG6 P&R | PASS | bitstream gerado; pinout 40/41/42/43/45/10 |
| DEBUG6 STA | PASS | 0 setup/hold; Fmax sys_clk 85,401 MHz |
| SRAM | PASS | operação 2; Flash não usada |
| SCK/WS | PASS | 500000,0 / 7812,5 Hz |
| SD | PASS | transições reapareceram após o reparo |
| PCM LEFT | PASS preliminar | 1024/1024 não-zero; signed positivo/negativo |
| frame errors | PASS | 0 |
| silêncio 4096 | PASS preliminar | AC RMS 3959,67; sem clipping |
| 500/1000/2000 Hz | FAIL atual | FFT não acompanha os estímulos |
| estímulo Razer | BLOQUEADO | matriz de microfones testemunha também não captou 1 kHz |
| taxa normal/pipeline/FSM | PENDENTE | depende de tom conhecido confirmado |

## Bitstream realmente programado

`C:\SAFE-FIELD\fpga\tp4-audio-inmp441\build\debug6_retest_after_contact_fix\impl\pnr\ao_0.fs`

SHA-256:
`7C1F24C7FE1B1142245AE53973B49C8A32807C6BFA77C27496D17C4CC3EA0B6F`

## Warnings

262 warnings preservados no log: 259 PA1001 de nets/carries/saídas não
consumidas pelo IP GAO e memórias com largura física maior que a largura útil;
2 TA1117 entre domínios do GAO tratados como assíncronos; 1 PR1014 da rota
genérica conhecida de `sys_clk_d`. Nenhum corresponde a violação de pinout ou
STA. BSRAM=10/10 é aceitável somente nesta instrumentação diagnóstica.

## Comandos principais desta rodada

```powershell
git switch -c tp4-retest-after-contact-fix
git commit --allow-empty -m "checkpoint: begin retest after contact fix"
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\Programmer\bin\programmer_cli.exe' --scan --cable-index 1
ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 safe-field@safe-field.local "pinctrl set 17 op dl; pinctrl get 17; date --iso-8601=seconds"
node sim\run-debug6-retest.mjs
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gw_sh.exe' 'scripts\build_debug6_retest_after_contact_fix.tcl'
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\Programmer\bin\programmer_cli.exe' --device GW1NSR-4C --operation_index 2 --frequency 2.5MHz --fsFile 'C:\SAFE-FIELD\fpga\tp4-audio-inmp441\build\debug6_retest_after_contact_fix\impl\pnr\ao_0.fs' --cable-index 1
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gao_sh.exe' -gao 'C:\SAFE-FIELD\fpga\tp4-audio-inmp441\build\debug6_retest_after_contact_fix\debug6_retest_after_contact_fix.rao' -out '<capture-prefix>' -device GW1NSR-4C -cable FT2CH -location 0
python scripts\capture_debug6_retest_stimulus.py '<stimulus>'
python scripts\analyze_debug6_retest_stimulus.py '<stimulus>' --expected-hz '<Hz>'
python scripts\verify_razer_acoustic_stimulus.py
```

A credencial SSH foi inserida apenas na sessão interativa e não está presente
em arquivos, scripts, logs, commits ou documentação.
