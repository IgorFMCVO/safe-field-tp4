# SAFE-FIELD — TP5

Aluno: Igor de Freitas Monteiro. Professor: Dácio Souza. Sistemas Digitais Embarcados / Instituto Infnet.

## Estado de fechamento em 13/09/2026

**Gates de software e hardware validados; PDF e ZIP finais gerados; somente o vídeo permanece pendente.** Começar por [RESULTADOS_FISICOS_TP5.md](docs_tp5/RESULTADOS_FISICOS_TP5.md).

- TP4 preservado; main permanece como baseline histórica.
- PR #1 / branch `tp5/final-integration-v1`.
- CI do handoff remoto de referência `4df9885230308ce822b881d8d2a4fa14fd7951eb`: SUCCESS; a revisão final deve usar o CI do commit publicado nesta branch.
- 23 verificações aritméticas RTL, hold/CRC/recuperação, OE e oito transações UART simuladas.
- 196 verificações ABI das funções Assembly e sete casos do cliente UART via PTY; ambos são evidência offline, não física.
- Cliente Assembly mede RTT_NS com CLOCK_MONOTONIC e valida resposta semanticamente; PING + 3 operações físicas PASS, burst 100/100 e estabilidade 600 s PASS.

O operador confirmou aquisição INMP441 física após reparo: voz/tom de 1 kHz, rodada final sem erros reportados. WAVs/hashes e fontes da imagem ficam no workspace local e ainda precisam ser vinculados à entrega. Preservar também a rodada de voz com erros UART. Não reabrir diagnóstico do microfone sem regressão nova.

## Estado físico final

JTAG GW1NSR-4C detectado e imagem SRAM final programada (SHA-256 `2672D28A5C72F980C53447EC7B3DCF7A953828F6336A9B91ADE2DAAC478D2F18`). Probe limpo confirmou GPIO14→pin 46, `rx_low_seen=true`, resposta válida e flags `0x94`. O smoke RAW24, áudio herdado e fotos do operador também são PASS. Coletores históricos de 600 s com falha foram preservados e explicados em `docs_tp5/RESULTADOS_FISICOS_TP5.md`.

## Aviso crítico

O top acadêmico remoto é de comandos/aritmética/telemetria v05. **Não é o streaming RAW24 local. Não programá-lo automaticamente sobre a imagem funcional.** A integração final precisa preservar o caminho acústico e reconciliar protocolo, baud, pinagem, fontes e bitstream. `i2s_rx_24.frame_error` é constante em zero nesta versão simplificada; não prova detecção de erros I²S. `sf_gpio_oe` é módulo demonstrativo isolado.

`docs_tp5/RELATORIO_TECNICO_TP5.md`, o PDF e o ZIP refletem os gates físicos finais. O vídeo segue `PENDENTE_LINK_FINAL`.

## Organização

`verilog_tp5/`: RTL, testbenches, CST/SDC e builds de simulação.
`assembly_tp5/`: fontes .S, includes, .a, ELF, testes e wrapper de execução nativa.
`docs_tp5/`: arquitetura, relatório, orientações e evidências.

Testar no Linux: `make -C verilog_tp5 test`; `make -C assembly_tp5 test`; `make -C assembly_tp5 disasm`. QEMU/PTY não são prova de hardware. No Pi físico, usar o wrapper somente após confirmar que a imagem/protocolo correspondem; ele não serve diretamente à UART RAW24 em uso.

O ZIP oficial só deve se chamar `Igor_Monteiro_PB_TP5.ZIP` depois de incluir a baseline final, relatório, .fs/netlist/STA, execução nativa, evidências, fotos e links reais. Vídeo TP5: até cinco minutos; apresentação final ao vivo: compromisso separado. Não publicar voz pessoal, segredos, DIAO ou a transcrição integral da aula no repositório público.
