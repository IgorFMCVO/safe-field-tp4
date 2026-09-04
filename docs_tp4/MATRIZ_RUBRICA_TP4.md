# Matriz da rubrica SAFE-FIELD TP4

Base de auditoria: lista de 22 requisitos fornecida pelo operador em 04/09/2026.
Não foi localizado no workspace um PDF separado do enunciado oficial nem o
relatório TP3; portanto não se inventam critérios adicionais.

| # | Requisito | Status | Evidência objetiva |
|---:|---|---|---|
| 1 | unidade aritmética Verilog | PASS | `safe_field_audio_energy_dsp.v`; square signed, 10/10 checks |
| 2 | BRAM funcional | PASS | `safe_field_energy_bram.v`; SDPB=1; leitura e média testadas |
| 3 | DSP dedicado | PASS | synthesis DSP=1; P&R MULT18X18=1 |
| 4 | waveforms | PASS | quatro VCDs e dois PNGs renderizados |
| 5 | teste físico Tang | PASS | áudio físico, GPIO17 e FPGA->Pi já aprovados |
| 6 | ARM64 multi-palavra | PASS | `ADDS/ADC` 128-bit no Pi 4 real |
| 7 | conversão inteiro/float | PASS | `SCVTF`, expected=-123456789,0, actual igual |
| 8 | lookup table | PASS | LUT de estados ARM64, válido/limite testados |
| 9 | masks/shifts/rotates | PASS | mix de protocolo, expected=actual |
| 10 | NEON inteiro | PASS | 8 lanes, energia exata igual ao escalar |
| 11 | NEON float | PASS | 4 lanes, erro máximo 0, tolerância 1e-7 |
| 12 | benchmark/paralelização | PASS | runs 50/200/800 reais preservados |
| 13 | arquitetura atualizada | PASS | `docs_tp4/ARQUITETURA_TP4.md` |
| 14 | ARM->FPGA | PASS | 3/3 vetores físicos; expected=actual; CRC=0; perdas=0 |
| 15 | FPGA->ARM | PASS | 3.264 mensagens, zero perda/erro, QUIET->ACTIVE->QUIET |
| 16 | checksum | PASS | CRC-8/ATM nos dois sentidos; corrupção rejeitada |
| 17 | telemetria | PASS | state, energy, frame counter, flags, sequence e JSONL |
| 18 | desempenho/latência | PASS | tabela de FPGA, UART, ARM64 e NEON |
| 19 | documentação | PASS | arquitetura, build, warnings, protocolos, resultados |
| 20 | PDF | PASS | `docs_tp4/output/pdf/RELATORIO_TECNICO_SAFE_FIELD_TP4.pdf` |
| 21 | ZIP | PASS | `Igor_Monteiro_PB_TP4.ZIP` com hashes verificados |
| 22 | vídeo | PASS | gravação publicada: https://youtu.be/1Ancm5QdG2E |

Resultado: **22/22 PASS**, 0 PARTIAL, 0 MISSING.

Todos os 22 requisitos da matriz têm evidência objetiva. O link final do Google
Drive permanece uma providência de submissão do operador, não um requisito
técnico adicional desta matriz.
