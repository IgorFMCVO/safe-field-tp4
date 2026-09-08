# SAFE-FIELD - Relatorio Tecnico TP5

**Aluno:** Igor de Freitas Monteiro  
**Disciplina:** Sistemas Digitais Embarcados  
**Projeto:** SAFE-FIELD  
**Plataformas-alvo:** Raspberry Pi Zero 2 W / Tang Nano 4K  
**Bancada de desenvolvimento:** Raspberry Pi 4 Model B / Tang Nano 4K GW1NSR-4C  
**Data:** setembro de 2026

## 1. Resumo

O TP5 consolida o SAFE-FIELD como prototipo embarcado ARM64-FPGA. A Tang Nano 4K executa aquisicao I2S, logica de atividade, unidades aritmeticas em ponto fixo e ponto flutuante, recepcao de comandos, CRC, handshaking e telemetria. O Raspberry executa codigo Assembly AArch64 modular, biblioteca estatica, syscalls Linux, manipulacao de buffers, conversoes de texto e montagem de quadros digitais. O projeto preserva a baseline TP4 e adiciona uma camada TP5 isolada, reproduzivel e testavel.

## 2. Evolucao TP1-TP5

TP1 definiu a arquitetura e os primeiros blocos. TP2 aprofundou hierarquia, loops e memoria. TP3 consolidou FSM, parser e primeira integracao ARM-FPGA. TP4 validou I2S, DSP, BSRAM, UART bidirecional, ARM64/NEON e desempenho. O TP5 transforma esses elementos em uma entrega final organizada por contratos: protocolo final, biblioteca Assembly, aritmetica fixa/flutuante, telemetria, casos de borda, testes e documentacao.

## 3. Arquitetura final

O fluxo academico final e `microfone/front-end -> I2S -> Tang Nano 4K -> processamento/estado -> UART -> Raspberry ARM64 -> SAFE-FIELD Core`. O enlace inverso `Raspberry -> UART -> Tang` envia comandos numericos com sequence e CRC. O GPIO17 permanece como caminho simples de observabilidade. O diagrama completo esta em `ARQUITETURA_FINAL_TP5.md`.

## 4. FPGA e Verilog

O top `safe_field_tp5_top.v` integra clock I2S, receptor de 24 bits, energia/FSM, UART RX/TX, parser de quadro, telemetria e unidades aritmeticas. O Q1.15 usa multiplicacao signed, shift aritmetico e saturacao. O bloco binary16 implementa multiplicacao de valores normais, zero, infinito e NaN; subnormais sao explicitamente tratados por flush-to-zero para reduzir custo de area, limitacao registrada e fora do caminho critico de audio.

A interface UART utiliza CRC-8/ATM. O receptor mantem `command_valid` ate `command_ready`, evitando perda por pulso de um ciclo. A transmissao usa `event_valid/event_ready`. Contadores separam comandos validos, CRC e framing errors. Um modulo `sf_gpio_oe.v` comprova controle de direcao/tri-state; os pinos funcionais da bancada possuem direcao fixa declarada nas constraints.

## 5. Protocolo digital final

ARM->FPGA usa 11 bytes: `A6 6A`, versao `05`, comando, sequence de 16 bits, payload de 32 bits e CRC. FPGA->ARM usa 12 bytes: `5A A5`, versao, tipo, sequence, data32, flags e CRC. Os comandos incluem PING, multiplicacao Q1.15, multiplicacao FP16 e leitura de contadores/energia.

## 6. Assembly ARM64 modular

`assembly_tp5` e dividido em IO/syscalls, buffers, parsing, aritmetica, protocolo e programas stand-alone. O Makefile produz `libsafe_field_tp5.a`, `tp5_demo` e `tp5_uart_demo`. O primeiro comprova parsing/conversao/protocolo sem libc; o segundo abre `/dev/serial0` por syscall, transmite PING e valida sync, sequence e CRC da resposta. `SYS_openat`, `SYS_read`, `SYS_write`, `SYS_close`, `SYS_clock_gettime` e `SYS_exit` sao chamados diretamente por `svc #0`. Macros parametrizadas padronizam stack e enderecamento.

## 7. Testes e casos de borda

Os testbenches cobrem Q1.15 positivo/negativo, limite e saturacao; FP16 normal, sinal, zero, overflow, NaN e underflow; CRC valido/invalido; OE/tri-state; e uma integracao top-level PING ARM->FPGA->UART com validacao de resposta e CRC. O CI compila o top, executa os VCDs, cross-compila AArch64, cria a biblioteca estatica, executa `tp5_demo` em QEMU e gera objdump.

## 8. Desempenho e estabilidade

A instrumentacao final usa `clock_gettime`/`perf_counter_ns` para RTT, sequence para perda, CRC/framing counters para integridade e logs com duracao. `assembly_tp5/tests/uart_performance.py` executa N round-trips reais e grava CSV/JSON com media, mediana, p95 e throughput. O gate fisico exige 10 minutos de telemetria continua. Valores TP5 fisicos so serao inseridos depois da sessao real; nenhum numero e estimado neste relatorio.

## 9. Hardware externo e pinout

O TP5 preserva o pinout fisicamente validado no TP4: 27 MHz no pin 45; GPIO17 no 40; I2S SCK/WS/SD nos 41/42/43; LED no 10; UART FPGA->Pi no 39; UART Pi->FPGA no 46, com a camera desconectada. A programacao TP5 deve ser feita inicialmente em SRAM para rollback seguro.

## 10. Raspberry Pi Zero 2 W x Pi 4

O enunciado define Raspberry Pi Zero 2 W. A bancada disponivel utiliza Raspberry Pi 4 Model B. Ambos suportam AArch64 com Raspberry Pi OS 64-bit, portanto o codigo Assembly e o protocolo permanecem portaveis. A diferenca fisica de plataforma e declarada e nao e ocultada.

## 11. Evidencia fisica e limitacao atual

A baseline TP4 ja comprovou comunicacao bidirecional, CRC, DSP/BSRAM, GPIO e operacao do Tang. Entretanto, o modulo INMP441 atualmente usado no ciclo de recuperacao do MVP apresentou resposta acustica anomala. A evidencia TP5 de audio sera produzida apenas depois da troca/contraprova do modulo. Isso evita transformar um defeito de bancada em evidencia academica falsa.

## 12. Integracao com o MVP SAFE-FIELD

O TP5 e o MVP compartilham o mesmo principio: FPGA para processamento deterministico e Raspberry para orquestracao. O TP5 nao usa estados QUIET/ACTIVE para interromper captura global de ocorrencia no MVP; a FSM de audio e um sinal/telemetria de segmentacao e observabilidade. A camada operacional completa continua preservando proveniencia e decisao humana.

## 13. Conclusao

A entrega TP5 deixa implementados e documentados os artefatos exigidos para arquitetura, Verilog avancado, protocolo bidirecional, Assembly modular, biblioteca estatica, syscalls, parsing, buffers, ponto fixo/flutuante, telemetria e testes. O unico gate que nao pode ser fabricado por software e a nova sessao fisica final com microfone funcional e o video de defesa. O pacote inclui checklist e roteiro para que esses dois passos sejam executados uma unica vez, sem retrabalho.
