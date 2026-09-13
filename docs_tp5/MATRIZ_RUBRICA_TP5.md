# Matriz da rubrica TP5

| Rubrica | Evidencia planejada/implementada |
|---|---|
| Arquitetura ARM-FPGA completa | FÍSICO_VERIFICADO/PASS; `ARQUITETURA_FINAL_TP5.md`, top Verilog e bibliotecas ARM64. |
| Assembly modular, biblioteca estatica, Makefile, macros, strings/buffers e conversoes | FISICO_VERIFICADO no Pi 4; stand-alone PASS, ABI 196/196, PTY 7/7 e referencia PASS; evidencias em `assembly_tp5/evidence/raspberry_native/`. |
| Handshaking, comandos, telemetria e erros | FÍSICO_VERIFICADO/PASS; probe limpo, flags `0x94`, checksum/framing/I²S/overrun zero; simulação WASM também PASS. |
| Ponto fixo e flutuante | FÍSICO_VERIFICADO/PASS; Q15 e FP16 reais conferidos contra valores esperados; `sf_fixed_q15_mac.v`, `sf_fp16_mul.v`, `tb_arithmetic.v`. |
| IO/OE | FÍSICO_VERIFICADO/PASS; pinout CST + `sf_gpio_oe.v` + `tb_gpio_oe.v`, probe limpo e SRAM final. |
| Sintese, P&R e STA | FISICO_VERIFICADO/PASS; bitstream SHA-256 `2672D28A5C72F980C53447EC7B3DCF7A953828F6336A9B91ADE2DAAC478D2F18`, 0 setup/hold violations. |
| FPGA->Pi RAW24 | FISICO_VERIFICADO/PASS; 3.966 frames/63.456 amostras em 3 s, CRC/perdas/frame errors = 0. |
| Pi->FPGA, bidirecionalidade | FÍSICO_VERIFICADO/PASS; PING + 3 operações, `COMMANDS_VERIFIED=4`, sequência e checksum sem erros. |
| Desempenho/estabilidade | FÍSICO_VERIFICADO/PASS; burst 100/100, 121,552 cmd/s e estabilidade 600 s, 597/597, sem perdas/erros. |
| Documentacao final | PASS; Markdown, PDF validado, manifesto, hashes e ZIP íntegro. |
| Video <=5 min | PENDENTE; roteiro em `ROTEIRO_VIDEO_TP5_5MIN.md`, link `PENDENTE_LINK_FINAL`. |
