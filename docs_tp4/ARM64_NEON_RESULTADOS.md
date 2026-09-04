# ARM64 e NEON no Raspberry Pi 4 real

Plataforma: Raspberry Pi 4 Model B Rev 1.5, Debian AArch64, kernel
6.18.34+rpt-rpi-v8, GCC 14.2.0.

## Funcional

| Caso | Esperado | Obtido | Resultado |
|---|---:|---:|---|
| add128 overflow, low | 0 | 0 | PASS |
| add128 overflow, high | 0 | 0 | PASS |
| add128 vetor, low | 18446744073709551615 | 18446744073709551615 | PASS |
| add128 vetor, high | 3689348814741910323 | 3689348814741910323 | PASS |
| inteiro -> double | -123456789,0 | -123456789,0 | PASS |
| LUT ACTIVE | 1 | 1 | PASS |
| LUT inválido | 255 | 255 | PASS |
| máscaras/shifts/rotate | 4076868206 | 4076868206 | PASS |
| NEON energia inteira | 21865754704 | 21865754704 | PASS |
| NEON float | tolerância 1e-7 | erro máximo 0 | PASS |

O `objdump` preservado comprova `ADDS`, `ADC`, `SCVTF`, `ROR`, `SMULL`,
`UADALP` e `FMUL` vetorial. A rotina inteira processa 8 elementos/vetor; a
rotina float processa 4.

## Benchmark real

| Repetições | INT escalar ns | INT NEON ns | Speedup | Float escalar ns | Float NEON ns | Speedup |
|---:|---:|---:|---:|---:|---:|---:|
| 50 | 11.067.481 | 3.412.555 | 3,243166x | 11.129.574 | 5.421.277 | 2,052943x |
| 200 | 42.972.741 | 4.492.092 | 9,566309x | 14.899.055 | 12.829.723 | 1,161292x |
| 800 | 58.673.389 | 17.922.667 | 3,273697x | 59.432.019 | 52.751.518 | 1,126641x |

Os valores são os observados, sem alegar frequência fixa de CPU ou speedup
idealizado.
