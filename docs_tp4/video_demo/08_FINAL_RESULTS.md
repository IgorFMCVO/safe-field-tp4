# SAFE-FIELD TP4 — resultados finais

- Rubrica: **22/22 PASS**, 0 PARTIAL, 0 MISSING;
- áudio físico INMP441 -> Tang: PASS;
- DSP dedicado: **1 MULT18X18**;
- BSRAM funcional: **1 SDPB**;
- simulação acadêmica: **40/40 checks PASS**;
- P&R / STA: PASS / PASS;
- ARM64: PASS no Raspberry Pi 4 real;
- NEON INT / FLOAT: PASS / PASS;
- FPGA -> ARM: PASS físico, 3.264 mensagens, perdas=0;
- ARM -> FPGA: **PASS físico, 3/3 comandos**;
- checksum errors / sequence losses / response errors: **0 / 0 / 0**;
- vídeo: gravado e publicado em https://youtu.be/1Ancm5QdG2E.

## Três vetores físicos

| Operand | Expected | Actual | Resultado |
|---:|---:|---:|---|
| 123 | 15129 | 15129 | PASS |
| -123 | 15129 | 15129 | PASS |
| 32767 | 1073676289 | 1073676289 | PASS |

Bitstream em SRAM:
`safe_field_tp4_official_bidirectional.fs`

SHA-256:
`6E4C460162816C54EE38B11CDA246004C05FE07CEC4C1FA963FDBB36092E172F`
