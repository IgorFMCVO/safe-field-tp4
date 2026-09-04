# Comandos de reprodução — SAFE-FIELD TP4

Execute na raiz do projeto original, não dentro do ZIP, usando PowerShell.

## Simulação final

```powershell
node sim\run-final-stable.mjs
```

Resultado esperado: quatro testbenches com `TEST_RESULT: PASS`, 26 checks e
zero erros.

## Síntese, P&R e STA

```powershell
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gw_sh.exe' scripts\build_safe_field_tp4_audio_stable_iter2.tcl
```

## Integridade do bitstream

```powershell
Get-FileHash -Algorithm SHA256 build\safe_field_tp4_audio_stable_iter2\impl\pnr\safe_field_tp4_validated.fs
```

## Programação SRAM — somente quando autorizada

```powershell
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\Programmer\bin\programmer_cli.exe' --device GW1NSR-4C --operation_index 2 --frequency 2.5MHz --fsFile build\safe_field_tp4_audio_stable_iter2\impl\pnr\safe_field_tp4_validated.fs --cable-index 1
```

Não selecionar operação de Flash. Conferir `docs/PINOUT_REQUIRED.md` antes de
qualquer programação ou intervenção física.
