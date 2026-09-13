# TP5 — orientações da aula de 11/09/2026

Fonte: VTT anexado pelo aluno, professor Dácio Souza. Tempos relativos à gravação. A transcrição automática tem termos corrompidos; não transformar trechos incertos em exigências novas.

| Tempo | Orientação sustentada | Aplicação |
|---|---|---|
| 09:11–12:22; 19:14–21:05 | Isolar hardware/alimentação/terra antes de condenar componente; usar código de diagnóstico. | Documentar SD zero, controle externo, reparo e aquisição recuperada. |
| 21:11–23:45 | Preservar escopo/competências; entrada/processamento na FPGA é caminho preferido. | Manter INMP441→Tang→Pi; não trocar frontend agora. |
| 25:40–26:43 | Conhecer o projeto para a arguição. | Estudar top, protocolo e operações, não só decorar relatório. |
| 28:11–29:28 | Testar fronteiras, antes/depois e overflow. | T−1/T/T+1, sinais, capacidade, parsing inválido e extremos. |
| 29:35–34:21 | Erro, falha, abortamento e recuperação podem exigir estados/logs diferentes. | STOP voluntário não deve causar reinício automático. |
| 34:35–35:17; 73:23–74:03; 79:24–82:14 | Calcular restrições temporais e conferir timing constraints. | Justificar SDC, clocks, janela, UART, buffers, RTT e STA da imagem final. |
| 38:03–40:09; 47:39–48:07 | Apresentação ao vivo obrigatória, colegas; até 20 min e cerca de 10 de perguntas. | Separar da gravação TP5 de até 5 min exigida no enunciado. |
| 41:45–42:47 | TP5 fecha projeto; final amplia relatório/retrospectiva/apresentação. | Congelar baseline após aceite, sem ampliar MVP nesta etapa. |
| 48:17–48:55; 77:23–77:43 | Prazo máximo; referência ao TP5 no domingo. | Usar 13/09/2026 23:59 conforme enunciado recebido, não confundir com entrega final dia 19. |
| 51:45–54:26 | Entender pinos/direções e RTL pronto; demonstrar competência simples quando fora da função principal. | Mapear I²S/UART reais e OE. Menções imprecisas a I²C não exigem acrescentar I²C ao projeto. |
| 54:54–61:05 | Saber explicar top, máscaras, shifts, registradores e decisões de otimização. | Mostrar a operação real e medição; não prometer ganho universal de shift+soma sem benchmark. |
| 74:15–76:07 | Dar utilidade ao sentido ARM→FPGA por modos, comandos ou parâmetros. | Demonstrar ação confirmada; não apenas retornar dados do sensor. |
| 76:11–77:07; 82:24–83:02 | Teste que encontra falha tem mérito; corrigir, não entregar fatal como PASS. | Manter execução falha histórica e regressão corrigida. |

## Limites da fonte

A aula não dispensa vídeo TP5, não autoriza chamar emulação de teste físico e não determina 600 s como duração oficial de estabilidade. Não há autorização inequívoca para substituir Pi Zero 2 W por Pi 4 na avaliação; declarar plataforma real e tratar aceitação com o professor. Não existe instrução para inserir biometria, câmera ou aconselhamento policial.

Separar no relatório orientação do professor, decisão de engenharia, resultado observado e limitação. Os exemplos de otimização do professor são argumentos para estudo, não garantia universal de velocidade na implementação.
