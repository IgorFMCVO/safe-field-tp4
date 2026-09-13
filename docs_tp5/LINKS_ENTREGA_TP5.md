# Links de entrega TP5

Repositorio GitHub: https://github.com/IgorFMCVO/safe-field-tp4

Branch alvo TP5: `tp5/final-integration-v1`

Video Google Drive: **PENDENTE_LINK_FINAL** (gravação/upload pelo operador, com presença do operador e acesso conferido).

Evidencias principais:

- Simulacao WASM: `docs_tp5/evidence/simulation/tp5_wasm_self_checking.log` — 5 testes PASS, `OVERALL_RESULT=PASS`.
- Bitstream final: `verilog_tp5/build/safe_field_tp5_final/impl/pnr/safe_field_tp5_final.fs` — SHA-256 `2672D28A5C72F980C53447EC7B3DCF7A953828F6336A9B91ADE2DAAC478D2F18`.
- Assembly nativo: `assembly_tp5/evidence/raspberry_native/` — stand-alone, ABI 196/196, PTY 7/7 e referencia PASS.
- Smoke fisico FPGA->Pi: `assembly_tp5/evidence/raspberry_native/physical_raw24_smoke.log` e `final_image_raw24_smoke_report.json` — 3.966 frames, 63.456 amostras, CRC/perdas/frame errors 0.
- Pi->FPGA: PASS físico; probe limpo com `rx_low_seen=true`, flags `0x94`, 1 resposta válida e zero erros.
- Estabilidade: PASS em `assembly_tp5/evidence/raspberry_native/tp5_uart_stability_600s_retry02.json` (600 s, 597/597).
- PDF: `docs_tp5/output/pdf/RELATORIO_TECNICO_SAFE_FIELD_TP5.pdf` — seis páginas, abertura e conteúdo validados.
- ZIP: `Igor_Monteiro_PB_TP5.ZIP` — integridade validada; SHA-256 informado em `docs_tp5/HASHES_SHA256.txt` e no fechamento.
