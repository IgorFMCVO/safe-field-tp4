# Resultados físicos TP5

**STATUS ATUAL: GATES DE SOFTWARE E HARDWARE PASS; PDF/ZIP PASS; VÍDEO PENDENTE.**

## Síntese, P&R e SRAM

- Dispositivo/JTAG: Gowin GW1NSR-4C (Tang Nano 4K); imagem final programada exclusivamente em SRAM.
- P&R: PASS; STA: 0 violações setup/hold, mínimo setup 13,379 ns e hold 0,558 ns.
- Bitstream `verilog_tp5/build/safe_field_tp5_final/impl/pnr/safe_field_tp5_final.fs`; SHA-256 `2672D28A5C72F980C53447EC7B3DCF7A953828F6336A9B91ADE2DAAC478D2F18`.
- Recursos: Logic 2169/4608 (48%), Registers 2252/3573 (64%), CLS 2030/2304 (89%), DSP 1/8 (13%).
- Warnings: 130 (129 PA1001 de dangling nets e 1 PR1014 de clock herdado das baselines); sem violations funcionais/timing.

## Simulação e Assembly

- WASM self-checking: `evidence/simulation/tp5_wasm_self_checking.log`, 5 testes PASS, `OVERALL_RESULT=PASS`.
- Assembly nativo no Raspberry Pi 4 Model B Rev 1.5: stand-alone PASS, ABI 196/196 PASS, PTY 7/7 PASS e referência PASS.
- Evidências: `assembly_tp5/evidence/raspberry_native/`.

## Comunicação física e operações numéricas

- Probe limpo: 2650 frames RAW24, 1 resposta válida, flags `0x94`, `rx_low_seen=true` e comando observado; checksum/framing/I²S/overrun = 0.
- PING + 3 operações: `COMMANDS_VERIFIED=4`, RTT total 2,464098 ms; Q15 `0x40004000` → `0x00002000` esperado/real; Q15 `0x80008000` → `0x00008000`; FP16 `0x3E004000` → `0x00004200`; checksum errors 0 e sequence loss 0.
- Smoke RAW24 final: 3966 frames/63456 amostras em 3 s, CRC/perdas/frame errors = 0.
- Rejeição/recuperação CRC: 1 frame inválido rejeitado, contador FPGA = 1, PING válido subsequente; SRAM recarregada limpa.

## Desempenho e estabilidade

- Burst: 100/100 comandos, 0 falhas; média 8,226915 ms, mediana 7,972805 ms, p95 11,895486 ms, 121,552 comandos/s.
- Estabilidade final: `assembly_tp5/evidence/raspberry_native/tp5_uart_stability_600s_retry02.json`, 600,001951519 s, 597/597 comandos, 791045 frames RAW24; perdas de sequência/origem, CRC, formato, checksum, framing, I²S e overrun = 0; RTT médio 1,747516 ms, mediana 1,645257 ms, p95 3,698757 ms.
- Dois coletores anteriores de 600 s são preservados como falhas históricas: primeiro 599/600 + 2 RAW corrompidos; segundo 600/600 + 2 RAW corrompidos. A causa foi starvation instrumental no byte/CRC Python; a coleta final em chunks/C CRC passou sem alteração RTL.

## Áudio, fotos e entrega

- Evidência acústica INMP441 após reparo permanece PASS e o smoke RAW24 da imagem final é PASS; razão espectral não é SNR calibrado.
- Fotos do operador estão em `evidence/photos/` e foram inseridas/indexadas.
- PDF final abre, contém seis páginas e passou conferência visual/textual; o ZIP final passou teste integral de todos os membros.
- Vídeo e link permanecem `PENDENTE_LINK_FINAL`, com operador presente obrigatoriamente.
