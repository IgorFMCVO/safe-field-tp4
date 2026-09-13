# SAFE-FIELD — fechamento TP5 no Codex local

## Missão

Executar o fechamento acadêmico com a bancada já funcional. Prazo fornecido: 13/09/2026, 23:59, America/Sao_Paulo. Não ampliar MVP, arquitetura de modelos, câmera, TLS ou diarização. Reservar tempo para vídeo e upload. Não parar depois de um plano: executar as tarefas independentes e apresentar somente os bloqueios reais.

## Gate acústico preservado

O operador informou INMP441 PHYSICAL ACOUSTIC CAPTURE: PASS após reparo de chicote/GND: voz coerente, tom de 1000 Hz, razão espectral local 169,46×, rodada final zero CRC/perdas/erros I²S no instrumento local. Não chamar essa razão de SNR calibrado. A gravação anterior de voz teve erros UART; preservar as rodadas separadamente.

Workspace: `C:\SAFE-FIELD\fpga\tp4-audio-inmp441`.
Relatório: `docs/mvp_operational/INMP441_ACOUSTIC_REVALIDATION_20260913.md`.
Evidências: `mvp/evidence/occurrence_recovery/p0_audio_sensitivity/post_ground_audio_20260913/`.
WAV voz: `20260913T182352611417Z_30f316ae_pcm16.wav`.
WAV tom: `20260913T182731032013Z_ac61a1df_pcm16.wav`.

Não trocar INMP441, mover fiação, repetir probes ou thresholds sem regressão demonstrada. Não presumir que o primeiro microfone foi comprovadamente defeituoso.

## A. Preservação e reconciliação

Registrar HEAD/branch/status e remotes sem expor credenciais. Guardar fontes, constraints, scripts e bitstream EXATOS que captaram voz, com hashes. Manter TP4 e alterações locais intactos: sem reset, clean, rebase, checkout destrutivo ou force-push.

Inspecionar a branch remota `tp5/final-integration-v1` de `IgorFMCVO/safe-field-tp4` em worktree/pasta separada. Não sobrescrever o workspace atual. O top TP5 remoto de comandos v05 a aproximadamente 115200 baud NÃO exporta RAW24 e NÃO é automaticamente a imagem física aprovada. Seu `i2s_rx_24.frame_error` é constante zero; `sf_gpio_oe` é demonstrador isolado. Não declarar esses dois itens como comprovados no hardware.

Selecionar uma baseline final coerente. Preferir preservar a captura funcional e incorporar apenas os itens TP5 necessários. Adaptar cliente Assembly ao protocolo realmente integrado sem reescrever o caminho acústico. Documentar perfis separados se usados, não apresentá-los como execução simultânea de uma única imagem.

## B. Testes offline e domínio dos contratos

Rodar Makefiles e suites. A .a reúne funções Assembly reais; o C é harness, Python é apoio. QEMU e PTY são simulação/emulação, não Pi/Tang físicos. O cliente agora registra RTT_NS por clock_gettime e testa cabeçalho, tipo, sequência, CRC, payload e status.

Distinguir resultado fixo alargado de 32 bits com 15 fracionários de narrowing Q1.15: −1×−1 =32768 no alargado; 32767 saturado no estreito. O buffer é cíclico de sobrescrita, não FIFO concorrente. Binary16 é perfil reduzido com truncamento/flush-to-zero, não IEEE 754 completo.

Cobrir T−1/T/T+1 nos dois limites, overflow/parsing inválido, capacidade insuficiente, EOF e IO parcial, CRC inválido/recuperação, hold valid/ready e wrap de sequência. Não remover asserções para obter PASS. Vincular cada log ao commit.

## C. Síntese e timing da imagem final

Na máquina com Gowin, gerar .fs, netlist, projeto reproduzível, CST, SDC, pinout, recursos e STA/P&R da baseline final. Registrar ferramenta/dispositivo/clock/hashes. Não renomear artefato TP4 para TP5.

Calcular tempos, taxas, payload/overhead e buffers. Com origem 2,7 MHz/64, há 42187,5 amostras/s por canal; PCM mono 24 bits exigiria 126562,5 bytes/s antes de overhead e não cabe em 115200 8N1. Documentar a configuração REAL do streaming local: baud, taxa transmitida e eventual decimação/filtro, sem inventá-los.

Justificar caminhos externos e clocks; não mascarar violações com false_path genérico. Se a cobertura de IO/timing estiver incompleta, declarar. Não chamar CI de STA.

## D. Sessão física final

Confirmar rollback e programar apenas SRAM quando necessário. Não usar Flash. Garantir um consumidor da UART e não aplicar wrapper v05 ao RAW24 sem compatibilidade.

Na Raspberry, registrar modelo real, uname -m, SO, ELF/commit/hash. Executar nativamente a biblioteca/cliente Assembly. Não alegar Pi Zero 2 W quando é Pi 4; a transcrição não contém autorização inequívoca de equivalência da plataforma.

Demonstrar comando útil ARM→FPGA, readback/ACK e telemetria, além de PING. Testar erro controlado/rejeição CRC e recuperação sem retirar fios energizados. Distinguir STOP voluntário, erro, timeout e recuperação; registrar lacuna se o comportamento não estiver implementado.

Medir RTT (n, média, mediana, p95, máximo), throughput útil e perdas; definir orçamento de resposta com justificativa. Não usar RTT/2 como latência de ida medida. Realizar 600 s de estabilidade como critério interno do projeto, não tempo literal da rubrica. Guardar falhas e sucesso; não apagar rodadas com erro.

Reutilizar a voz/tom existentes se núcleo/imagem forem os mesmos. Se a imagem for modificada, uma regressão acústica curta basta. Waveform simulada e captura física devem ter legendas diferentes.

## E. Documentação e entrega

Aplicar `ORIENTACOES_AULA_11_09.md`. Atualizar relatório antigo: o microfone não está mais aguardando substituição. Diagramar a baseline FINAL; descrever módulos, rotinas, protocolos, OE, formatos, limites, timing e decisões. Explicar o reparo e a diferença entre CRC de transporte e conteúdo acústico válido.

Cada evidência: arquivo, SHA-256, comando, data, plataforma, imagem. Não publicar WAV pessoal nem VTT integral em Git público; no ZIP acadêmico incluir somente material autorizado e sem terceiros. Não inventar fotos, resultados, prints ou links.

Gerar PDF legível e conferir todas as páginas. Incluir fontes comentados no ZIP e trechos críticos no PDF. Matriz: IMPLEMENTADO/SIMULADO/EMULADO/FÍSICO_VERIFICADO/PENDENTE.

Vídeo TP5: tela+webcam, até 5 minutos, hardware real, conta Drive acadêmica e acesso de visualização conferido. A apresentação ao vivo de até 20 minutos mencionada na aula não substitui esse vídeo. O operador precisa aparecer; não fabricar depoimento.

Gerar `Igor_Monteiro_PB_TP5.ZIP` somente depois dos gates e links reais. Incluir verilog_tp5, assembly_tp5, docs_tp5, .a/ELF, .fs/netlist/constraints/STA, VCDs, fotos, logs, PDF e links. Excluir .git, venvs, modelos, DIAO e segredos. Reabrir em pasta limpa e verificar hashes/caminhos.

## Retorno obrigatório

Commit final; imagem/hash; CI; Assembly nativo; bidirecional; síntese/STA; estabilidade; RTT/p95/throughput; áudio; fotos; PDF; ZIP/hash; link GitHub; vídeo; pendências reais. Não afirmar entrega concluída se algum requisito obrigatório não foi comprovado.
