# Checklist final TP5

## Ja preparado

- [x] `/verilog_tp5` estruturado.
- [x] `/assembly_tp5` estruturado em multiplos modulos.
- [x] biblioteca estatica prevista no Makefile.
- [x] syscalls Linux AArch64.
- [x] buffers/strings/conversoes/macros.
- [x] ponto fixo Q1.15.
- [x] floating point binary16 com limites documentados.
- [x] protocolo UART com CRC e handshaking.
- [x] telemetria minima e contadores de erro.
- [x] OE/tri-state testavel.
- [x] testbenches e CI preparados.
- [x] arquitetura, protocolo, rubrica e roteiro de video.

## Evidencias concluidas

- [x] gerar e salvar bitstream TP5 no Gowin; P&R/STA PASS, sem violations.
- [x] programar a imagem final na Tang em SRAM.
- [x] executar smoke físico FPGA->Pi: 3966 frames/63456 amostras em 3 s, CRC/perdas/frame errors = 0.
- [x] comprovar Pi->FPGA e bidirecionalidade: probe limpo, resposta válida, flags `0x94`, zero erros.
- [x] validar PING + 3 operações numéricas e rejeição/recuperação CRC.
- [x] executar Assembly nativo no Raspberry Pi 4: stand-alone PASS, ABI 196/196 PASS, PTY 7/7 PASS e referencia PASS.
- [x] executar burst 100/100 e estabilidade final de 600 s sem perdas/erros.
- [x] atualizar `RESULTADOS_FISICOS_TP5.md` somente com dados medidos.

## Pendencias e limites reais

- [x] inserir fotos/prints fornecidos pelo operador, quando selecionados para a entrega.
- [ ] gravar video <=5 min com webcam.
- [ ] publicar video no Google Drive e inserir link (`PENDENTE_LINK_FINAL`).
- [x] gerar e validar PDF/ZIP final.
