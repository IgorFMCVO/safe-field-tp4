# SAFE-FIELD — stable cued diagnostic

Data: 04/09/2026, America/Sao_Paulo. Branch:
`tp4-retest-after-contact-fix`. Variante separada; nenhum build anterior foi
sobrescrito. Programação exclusivamente SRAM, operação 2.

## Implementação

- `THRESHOLD_ON=12000`, `THRESHOLD_OFF=6000`.
- ataque: 2 janelas completas de 256 frames.
- retenção mínima ACTIVE: 82 janelas, aproximadamente 498 ms.
- liberação: 16 janelas consecutivas abaixo de OFF.
- LED de diagnóstico: somente GPIO17; a FSM é observada exclusivamente no GAO.
- pinout preservado: 45/sys_clk in, 40/GPIO17 in, 41/SCK out, 42/WS out,
  43/SD in pull-down e 10/LED out.

## Verificação de build

- Simulação auto-verificável: PASS, 11 checks, 0 erros.
- Síntese/P&R: PASS.
- STA: PASS, zero endpoints setup/hold violados e TNS=0; Fmax de `sys_clk`
  31,761 MHz para requisito de 27,000 MHz.
- Recursos: Logic 871/4608 (19%), Register 573/3573 (17%), CLS 640/2304
  (28%), BSRAM 10/10 (100%).
- Warnings: 331 — 1 NL0002 (wrapper GPIO achatado), 327 PA1001
  (saídas/carries não consumidos do GAO/BSRAM/receptor), 2 TA1117
  (relações de domínios observacionais) e 1 PR1014 (rota genérica conhecida
  de `sys_clk_d`). Nenhum warning foi ocultado.

Bitstream:
`C:\SAFE-FIELD\fpga\tp4-audio-inmp441\build\stable_cued_capture\impl\pnr\ao_0.fs`

SHA-256:
`99E43D60FBCE01CFBC6270624C4741AAB9DF30D69DE4D34B6031CEC2416639E7`

JTAG antes da programação: GW1NSR-4C, ID `0x0100981B`, FT2CH 2,5 MHz.
SRAM Program: PASS, 100%, User Code `0x0000CC9F`, Status Code `0x0003F020`.

## Capturas

- `stable_cued_fsm_10cycles_01`: marcação inicialmente interpretada com
  polaridade incorreta; INCONCLUSIVE.
- `stable_cued_fsm_10cycles_02`: 10 intervalos presentes, mas instrução ao
  operador foi baseada em polaridade ainda não confirmada; INCONCLUSIVE.
- `stable_cued_fsm_5longcycles_01`: operador confirmou que não falou;
  INCONCLUSIVE, não FAIL.
- `stable_cued_fsm_5longcycles_02`: marcação invertida; INCONCLUSIVE.
- Teste estático posterior: operador confirmou `GPIO17 LOW -> LED apagado`;
  portanto `GPIO17 HIGH -> LED aceso` é a marca correta.
- `stable_cued_fsm_5longcycles_03_valid`: quatro janelas completas exportadas;
  frame errors=0, overflow=0; uma janela forte atingiu energia média 17900
  contra 5692 adjacente (3,145x). Falta confirmação pós-captura do operador.
- `stable_cued_fsm_10cycles_04_valid`: pulso de pré-trigger seguido de dez
  ciclos 4 s HIGH/4 s LOW. O CSV contém nove intervalos completos e as bordas
  do pulso/décimo intervalo; todas as nove janelas completas observaram ACTIVE
  e retorno a QUIET, frame errors=0. O quantizador GAO `energy[17:4]` saturou
  em picos (`energy_overflow=1`), sem overflow no acumulador do pipeline. A FSM
  apresentou 100 transições em 99,42 s. O operador confirmou que falou nos
  intervalos acesos, com ressalva de possível ciclo pulado: detecção 9/9
  intervalos completos PASS, estabilidade FAIL; não se alega 10/10.

## Comandos principais

```powershell
node sim/run-stable-cued.mjs
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gw_sh.exe' 'scripts\build_stable_cued_capture.tcl'
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\Programmer\bin\programmer_cli.exe' --scan --cable-index 1
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\Programmer\bin\programmer_cli.exe' --device GW1NSR-4C --operation_index 2 --frequency 2.5MHz --fsFile 'build\stable_cued_capture\impl\pnr\ao_0.fs' --cable-index 1
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gao_sh.exe' -gao 'src\safe_field_stable_cued_capture.rao' -out '<capture-prefix>' -device GW1NSR-4C -cable FT2CH -location 0
python scripts/analyze_energy_capture.py '<capture-prefix>' --threshold-on 12000 --threshold-off 6000
```

A senha SSH foi fornecida somente à sessão interativa e não foi persistida.

## Candidato funcional carregado ao final

Top `safe_field_stable_audio`, mesma lógica temporal e LED controlado por
`GPIO17 OR sound_active`. Simulação 10/10 PASS; P&R PASS; STA PASS, zero
violações setup/hold, Fmax 29,638 MHz para 27 MHz. Recursos: Logic 358/4608
(8%), Register 160/3573 (5%), CLS 244/2304 (11%). Warnings: 1 NL0002 e 1
PR1014, ambos já analisados; nenhum warning ocultado.

Bitstream atualmente em SRAM:
`C:\SAFE-FIELD\fpga\tp4-audio-inmp441\build\stable_audio_candidate\impl\pnr\safe_field_stable_audio.fs`

SHA-256:
`D5F94C664BB1882437CA3BD235A70913F00E1419C17C7943A33CEA64D80E7858`

SRAM Program operação 2: PASS, 100%, GW1NSR-4C `0x0100981B`, User Code
`0x00003D33`, Status Code `0x0003F020`. O build final preservado mantém SHA-256
`0B04C9DF3F51B408932ED75B754F7F180001F02C50594B14CC685B4CE1BFFE8B`.
