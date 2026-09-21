# Resultados finais para a demonstração TP5

- Imagem final: `safe_field_tp5_final.fs` — SHA-256 `2672D28A5C72F980C53447EC7B3DCF7A953828F6336A9B91ADE2DAAC478D2F18`.
- Gowin: síntese/P&R/STA PASS; setup/hold = 0 violações; Fmax 42,268 MHz @ 27 MHz.
- Assembly AArch64 nativo no Raspberry Pi 4 Model B Rev 1.5: PASS; ABI 196/196.
- Comunicação física: PING + três operações úteis, 4/4; checksum errors = 0; sequence losses = 0.
- Q15 `0x40004000`: esperado/real `0x00002000`.
- Q15 `0x80008000`: esperado/real `0x00008000`.
- FP16 `0x3E004000`: esperado/real `0x00004200`.
- Burst físico: 100/100; p95 11,895486 ms; 121,552 comandos/s.
- Estabilidade física: 600,001951519 s; 597/597; 791045 RAW24; perdas/CRC/framing/I²S/overrun = 0; p95 3,698757 ms.
- Áudio: voz física coerente; tom esperado/observado 1.000,0 Hz; smoke RAW24 final sem erros.
- Rejeição CRC: frame inválido rejeitado e comando válido subsequente aceito; imagem final recarregada em SRAM limpa.
- Vídeo: `PENDENTE_LINK_FINAL`.

Os ensaios com QEMU/PTY são rotulados como offline. Os resultados físicos acima usam Tang Nano 4K e Raspberry Pi 4 reais.
