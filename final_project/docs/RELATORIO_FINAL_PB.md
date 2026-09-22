# SAFE-FIELD — relatório de consolidação do Projeto de Bloco

**Aluno:** Igor de Freitas Monteiro. **Professor:** Dácio Souza. **Instituição:** Instituto Infnet. **Disciplina:** Sistemas Digitais Embarcados. **Consolidação final:** 22/09/2026.

## 1. Objeto e fronteira da entrega

O projeto iniciou como uma proposta de apoio ao registro de ocorrências e evoluiu para uma prova embarcada verificável. A versão técnica final combina aquisição física de áudio INMP441, recepção I²S na Tang Nano 4K, transporte RAW24/PCM16 para a Raspberry Pi 4 e comandos ARM64 com respostas numéricas verificadas. Não entrega reconhecimento facial, veracidade automática de relatos, análise jurídica operacional ou um produto de campo certificado.

O Assessment não exige desenvolvimento novo obrigatório. Esta revisão organiza o conjunto TP1–TP5, explicita as mudanças de escopo e conserva a baseline validada `72759423a1e06e3b2eef5721e75679a56ea3a2ee`. O PDF geral inclui o relatório técnico detalhado TP5 como anexo identificado, sem apagar os relatórios históricos nem reutilizar datas antigas para novas medições.

## 2. Retrospectiva TP1–TP5

### TP1 — concepção e primeiros blocos

O pacote histórico recuperado contém Assembly inicial, score combinacional, FSM demonstrativa, testbenches e evidências de VM. O score inicial era uma agregação acadêmica de indicadores, não detector de mentira. Planejamentos com câmera e interpretação posterior são visão inicial, não capacidades comprovadas da versão final. A ausência de hardware nas etapas iniciais é preservada como limitação histórica.

### TP2 — hierarquia, memória e depuração

A etapa acrescenta empacotamento de indicadores, lógica combinacional de decisão e top hierárquico. O Assembly percorre um vetor em memória, calcula e armazena score/classe, com LDR/STR, comparações, loops e depuração GDB. A comunicação física permanece planejada. O pacote recuperado inclui fontes, ELF, logs e imagens de simulação/execução; o PDF histórico contém estados de evidência previstos que não são reescritos retroativamente.

### TP3 — controle sequencial e interface lógica

A FSM hierárquica usa IDLE, READY, COLLECTING, ANALYZING, RESULT, CLOSED e ERROR. O protocolo paralelo lógico de oito bits distingue tipos nos bits superiores e conteúdo nos inferiores. Timeout, quadro inválido e recuperação explícita são exercitados. Assembly acrescenta parser e tabela de salto. A síntese e o place-and-route foram registrados, mas a comunicação física entre placas ainda não tinha sido realizada nessa etapa. A interface de oito bits é histórica e não deve ser confundida com os quadros UART finais.

### TP4 — aquisição digital e recursos avançados

A baseline `cbf0a49c82bbdbc5411bb4e4d3b0afac2a2056d8` registra I²S, DSP, memória de energia/BRAM, comunicação UART e rotinas ARM64/NEON. Esses arquivos são preservados em `assembly_tp4`, `verilog_tp4` e `docs_tp4`. Rotinas NEON e memória histórica são evidência dessa etapa; não se afirma que todas estão instanciadas no top TP5.

### TP5 — coexistência, biblioteca e validação integrada

A imagem final conserva a captura acústica e acrescenta comandos v05, aritmética Q1.15/binary16 e arbitragem de UART. A biblioteca estática contém módulos temáticos e executáveis sem libc sob Linux. A validação inclui simulação, síntese/STA, execução nativa, comandos físicos, rajada e estabilidade de 600 segundos. Os erros e correções anteriores permanecem registrados.

## 3. Arquitetura final e decisões

INMP441 → I²S → FPGA → UART → Raspberry → RAW/WAV. No sentido inverso: cliente Assembly → comando com sequência/CRC → FPGA → operação → resposta verificada. O clock de sistema é de 27 MHz. A Raspberry efetivamente medida foi Pi 4 Model B Rev 1.5; não há medição equivalente no Zero 2 W exigido pelo enunciado.

A FPGA executa temporização e circuitos digitais; o ARM executa rotinas sob Linux, protocolo e controle. No top final, `led = pi_signal`: o LED demonstra o GPIO, não detecção autônoma de voz. O observador chamado `energy` calcula média da magnitude absoluta por janela, não RMS. QUIET/ACTIVE não interrompem a captura I²S.

A UART é compartilhada somente entre pacotes: um RAW24 iniciado termina antes da resposta; `response_launched` evita lançamento duplicado. Dois bancos não constituem armazenamento ilimitado. Overrun e contadores tornam visíveis os limites do transporte.

## 4. Implementação e contratos

Comandos ARM→FPGA têm 11 bytes; respostas têm 12; ambos usam CRC-8/ATM. RAW24 usa pacote de 95 bytes para 16 amostras RAW24/PCM16 e CRC-16. O cliente verifica sync, versão, tipo, sequência, CRC, payload e flags. CRC correto não substitui a verificação semântica do resultado.

Assembly é organizado em IO/syscalls, buffers, parsing, aritmética e protocolo. Trata IO parcial, EOF, EINTR e capacidade. `svc #0` usa serviços do Linux: ausência de libc não significa bare-metal. Rotinas não-leaf preservam LR conforme necessário. NEON e GPIO de etapas anteriores ficam classificados como históricos quando não fazem parte do cliente final.

Q1.15 usa operandos signed16 com quinze bits fracionários. O produto ajustado -32768 × -32768 retorna 32768 em saída alargada; o narrowing Q1.15 satura em 32767. A soma multi-palavra usa ADDS/ADC, módulo 2^128. O multiplicador binary16 tem truncamento e flush-to-zero; não é implementação IEEE 754 integral.

## 5. Resultados e capacidade

- ABI nativa: 196/196 no Pi 4. PTY é teste serial de software, mesmo quando nativo.
- Físico: PING + três operações corretas; checksum/perdas zero.
- Rajada: 100/100 comandos, média 8,226915 ms, p95 11,895486 ms, 121,552 comandos/s.
- Estabilidade: 600,001951519 s; 597/597 comandos; 791.045 quadros RAW24, equivalentes a 12.656.720 amostras. Contadores zero na rodada final.
- Gowin: Fmax 42,268 MHz, clock 27 MHz, slack setup 13,379 ns e hold 0,558 ns; zero violações reportadas e warnings preservados.
- Smoke final: 3.966 quadros, 63.456 amostras, zero erros. Revalidação acústica histórica: voz coerente e tom de 1 kHz.

A origem I²S é 42.187,5 amostras/s/canal; o diagnóstico usa stride 2, transportando 21.093,75. UART 1.500.000 baud em 8N1 oferece 150.000 bytes/s; o formato demanda aproximadamente 125.244 bytes/s, 83,496% da capacidade antes de respostas/intervalos. A redução por stride não é apresentada como filtro antialias. RTT não é latência acústica nem prazo hard real-time do Linux. O ensaio contínuo enviou aproximadamente um comando por segundo; a rajada mede outra condição.

## 6. Diagnóstico, limites e próximos passos

O bloqueio SD zero foi superado após reparo de contatos/reconexão. Transporte válido de zeros não demonstrava captação; foi necessário observar a linha e comparar estímulos físicos. O defeito do primeiro microfone não foi comprovado. A voz original tem ruído perceptível informado pelo autor; captação funcional não equivale a qualidade de campo. O áudio não foi tratado para ocultar essa limitação.

Os primeiros coletores longos tiveram falhas; a coleta em blocos/CRC em C resolveu a rodada final sem alteração RTL, conforme registro de bancada. Não se generaliza uma janela limpa para confiabilidade ilimitada.

OE/tri-state dinâmico é demonstrador simulado. A BRAM/NEON histórica é apontada com a versão correspondente. PLL e DDR/SerDes não são apresentados como implementados na versão final. O SDC declara o clock principal; zero violações não prova modelagem completa de todos os atrasos externos. Essas limitações integram a avaliação, não dispensam automaticamente itens da rubrica.

Melhorias futuras: front-end acústico e montagem, caracterização espectral, filtragem/reamostragem adequada, orçamento temporal externo mais completo e ensaios de maior duração/carga. Não foram implementadas nesta consolidação.

### Demonstração operacional final - 22/09/2026

Após a consolidação da baseline técnica, foi realizada uma demonstração operacional complementar, sem reclassificar os ensaios técnicos anteriores. A ocorrência exibida no vídeo final é `20260922T054343Z_6db89a43`: estado `FINISHED`, arquivo `raw.wav` com 37,45 s, 49.367 quadros válidos, transcrição persistida e visível no dashboard e segmento `segment_0001` indicado como `COMPLETE`. O painel read-only carrega as evidências diretamente do armazenamento e permite reproduzir o áudio original.

A captura de tela final preserva também o histórico do processamento, por isso o cabeçalho apresenta `COMPLETE / REJECTED conforme lista`. A análise estruturada mostrada nessa ocorrência contém listas vazias de fatos capturados, hipóteses inferidas e confirmações do policial. Portanto, a demonstração comprova captura, persistência, reprodução e transcrição, mas não é apresentada como prova de diarização multi-interlocutor robusta, análise jurídica automática ou geração definitiva de BO/REDS.

Vídeo final no Google Drive: https://drive.google.com/file/d/1Pjdgc01Xwe8fCwiFhzkd-NzHbMATUtnK/view?usp=drive_link


## 7. Rastreabilidade, evidências e entrega

Os arquivos sob `final_project/assembly_tp5`, `verilog_tp5` e `docs_tp5` mantêm os nomes de origem para preservar builds e referências. O ZIP institucional reúne o relatório geral, essa árvore final e o histórico recuperado dos TPs. Há manifesto SHA-256 e conferência de integridade. O bitstream da cópia institucional conserva SHA-256 `2672D28A5C72F980C53447EC7B3DCF7A953828F6336A9B91ADE2DAAC478D2F18`; exportações Git podem normalizar finais de linha, devendo ser conferidas antes de programação.

O relatório detalhado TP5 integra o PDF geral como anexo, com diagramas, waveform, fotos e dados. As etiquetas TP5 do anexo identificam a etapa que produziu as medições. Os ensaios técnicos da baseline não foram repetidos na consolidação; em 22/09 foi realizada a demonstração operacional complementar descrita acima. O uso de IA como apoio à implementação e documentação não substitui a demonstração individual de aprendizado e a arguição.

Vídeo final: https://drive.google.com/file/d/1Pjdgc01Xwe8fCwiFhzkd-NzHbMATUtnK/view?usp=drive_link
Código técnico: https://github.com/IgorFMCVO/safe-field-tp4/tree/72759423a1e06e3b2eef5721e75679a56ea3a2ee
CI: https://github.com/IgorFMCVO/safe-field-tp4/actions/runs/34782568776

O vídeo final foi fornecido pelo autor em Google Drive. Antes da submissão, recomenda-se apenas conferir o compartilhamento em uma janela anônima. A entrega no Moodle e a apresentação ao vivo permanecem atos separados deste pacote.

## Fontes locais

Enunciado final fornecido; transcrição de 18/09 (diretrizes administrativas e de defesa); pacotes históricos `safe_field_tp1_entrega_final (1).zip`, `igor_monteiro_PB_TP2.zip`, `igor_monteiro_PB_TP3(1).zip`; baseline TP4; fontes e evidências técnicas de `7275942`; relatório final TP5 de nove páginas; demonstração operacional de 22/09/2026 e captura do dashboard final. As conclusões de cada etapa conservam o alcance original das evidências.
