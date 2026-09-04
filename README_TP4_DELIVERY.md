# SAFE-FIELD TP4 — reprodução do build final

Requer Gowin Designer Education V1.9.11.03 e Node.js. Execute em PowerShell a
partir deste diretório.

```powershell
node sim\run-final-stable.mjs
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gw_sh.exe' scripts\build_safe_field_tp4_audio_stable_iter2.tcl
Get-FileHash -Algorithm SHA256 build\safe_field_tp4_audio_stable_iter2\impl\pnr\safe_field_tp4_validated.fs
```

Resultado esperado: todos os testbenches `TEST_RESULT: PASS`, P&R completo,
zero endpoints setup/hold violados e SHA-256
`5D8F2D31EF5D0349AC0E52F13AC8A7472FCB1A23103131D13163BB8946F39181`.

Programação física, somente quando autorizada e apenas em SRAM:

```powershell
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\Programmer\bin\programmer_cli.exe' --device GW1NSR-4C --operation_index 2 --frequency 2.5MHz --fsFile build\safe_field_tp4_audio_stable_iter2\impl\pnr\safe_field_tp4_validated.fs --cable-index 1
```

Não usar operações de Flash. Câmera DVP deve permanecer desconectada. Consulte
`PINOUT_REQUIRED.md` antes de qualquer intervenção física.
