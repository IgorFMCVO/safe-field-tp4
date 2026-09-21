# SAFE-FIELD — entrega final do Projeto de Bloco

Aluno: Igor de Freitas Monteiro. Instituto Infnet. Professor: Dácio Souza.
Consolidação documental: 21/09/2026. Baseline técnica preservada: `72759423a1e06e3b2eef5721e75679a56ea3a2ee`.

Esta pasta organiza o código final, bibliotecas, executáveis, imagens da FPGA, diagramas, relatórios de implementação e evidências do TP5 para o Assessment. Não modifica a lógica validada, não reprograma hardware e não promove testes simulados a testes físicos.

- `assembly_tp5/`: fontes AArch64, biblioteca estática, executáveis e testes/evidências nativas.
- `verilog_tp5/`: RTL, testbenches, constraints, bitstream e relatórios Gowin.
- `docs_tp5/`: documentação técnica e evidências preservadas da etapa técnica.
- `docs/RELATORIO_FINAL_PB.md`: consolidação de escopo, retrospectiva e limites do projeto completo.
- `scripts/`: ferramentas originais; nomes TP5 mantidos para conservar caminhos relativos e rastreabilidade.

## Execução

Executar os Makefiles a partir desta pasta: `make -C verilog_tp5 test`, `make -C assembly_tp5 test` e `make -C assembly_tp5 disasm`. Requer toolchains declaradas nos READMEs. Estes comandos não fazem nova programação física. Scripts de hardware exigem conferência de baud/protocolo, posse exclusiva da UART, modelo da Raspberry e rollback.

## Resultado técnico de referência

Pi 4 Model B Rev 1.5; ABI nativa 196/196; PING e três operações físicas; 600 s com 597/597 respostas e 791.045 quadros RAW24 sem erros na rodada final. Rajada: 100/100, p95 11,895486 ms e 121,552 comandos/s. STA: zero violações reportadas, Fmax 42,268 MHz, clock utilizado 27 MHz. São resultados da sessão de 13/09, não ensaios repetidos em 21/09.

## Vídeo e entrega

Vídeo fornecido pelo autor: https://www.loom.com/share/dd65ae3944f94fa897e1196fe789a90b
CI técnico: https://github.com/IgorFMCVO/safe-field-tp4/actions/runs/34782568776

O ZIP institucional se chama `Igor_Monteiro_PB.ZIP`; o relatório consolidado é `RELATORIO_FINAL_PROJETO_SAFE_FIELD.pdf`. Ambos são entregues diretamente ao autor. O ZIP também contém os arquivos históricos recuperados TP1–TP5. O PDF TP5 que permanece nesta árvore é o documento histórico do checkpoint técnico, não o relatório geral novo.

A orientação institucional pede hospedagem no Google Drive acadêmico. O link recebido é Loom; não se presume aceite da substituição nem reprodução/acesso/duração verificados. Não houve submissão automática ao Moodle. A demonstração e a arguição ao vivo são separadas.
