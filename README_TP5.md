# SAFE-FIELD — TP5

Aluno: Igor de Freitas Monteiro. Professor: Dácio Souza. Sistemas Digitais Embarcados / Instituto Infnet.

## Estado de fechamento em 13/09/2026

**Base de software candidata validada em CI; entrega final ainda depende da reconciliação com a bancada.** Começar por [FECHAR_TP5_NO_CODEX.md](docs_tp5/FECHAR_TP5_NO_CODEX.md).

- TP4 preservado; main permanece como baseline histórica.
- PR #1 / branch `tp5/final-integration-v1`.
- CI da revisão de código `71b8cd2f0016ebee65148e7057c92577f2029d6d`: [run 34777177908](https://github.com/IgorFMCVO/safe-field-tp4/actions/runs/34777177908), success.
- 23 verificações aritméticas RTL, hold/CRC/recuperação, OE e oito transações UART simuladas.
- 190 verificações das funções Assembly reais via QEMU; oito casos do cliente UART via PTY.
- Cliente Assembly mede RTT_NS com CLOCK_MONOTONIC e valida resposta semanticamente.

O operador confirmou aquisição INMP441 física após reparo: voz/tom de 1 kHz, rodada final sem erros reportados. WAVs/hashes e fontes da imagem ficam no workspace local e ainda precisam ser vinculados à entrega. Preservar também a rodada de voz com erros UART. Não reabrir diagnóstico do microfone sem regressão nova.

## Aviso crítico

O top acadêmico remoto é de comandos/aritmética/telemetria v05. **Não é o streaming RAW24 local. Não programá-lo automaticamente sobre a imagem funcional.** A integração final precisa preservar o caminho acústico e reconciliar protocolo, baud, pinagem, fontes e bitstream. `i2s_rx_24.frame_error` é constante em zero nesta versão simplificada; não prova detecção de erros I²S. `sf_gpio_oe` é módulo demonstrativo isolado.

`docs_tp5/RELATORIO_TECNICO_TP5.md` e os checklists originalmente criados antes da recuperação acústica são rascunhos a atualizar; referências antigas a microfone ainda aguardando troca estão superadas. O status e a ordem de fechamento deste README/handoff prevalecem sobre essas pendências históricas. Não apresentar um rascunho antigo como relatório final.

## Organização

`verilog_tp5/`: RTL, testbenches, CST/SDC e builds de simulação.
`assembly_tp5/`: fontes .S, includes, .a, ELF, testes e wrapper de execução nativa.
`docs_tp5/`: arquitetura, relatório, orientações e evidências.

Testar no Linux: `make -C verilog_tp5 test`; `make -C assembly_tp5 test`; `make -C assembly_tp5 disasm`. QEMU/PTY não são prova de hardware. No Pi físico, usar o wrapper somente após confirmar que a imagem/protocolo correspondem; ele não serve diretamente à UART RAW24 em uso.

O ZIP oficial só deve se chamar `Igor_Monteiro_PB_TP5.ZIP` depois de incluir a baseline final, relatório, .fs/netlist/STA, execução nativa, evidências, fotos e links reais. Vídeo TP5: até cinco minutos; apresentação final ao vivo: compromisso separado. Não publicar voz pessoal, segredos, DIAO ou a transcrição integral da aula no repositório público.
