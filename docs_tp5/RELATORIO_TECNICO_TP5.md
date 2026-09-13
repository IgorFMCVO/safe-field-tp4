# SAFE-FIELD - Relatorio Tecnico TP5

**Aluno:** Igor de Freitas Monteiro  
**Disciplina:** Sistemas Digitais Embarcados  
**Projeto:** SAFE-FIELD  
**Plataformas-alvo:** Raspberry Pi Zero 2 W / Tang Nano 4K  
**Bancada de desenvolvimento:** Raspberry Pi 4 Model B / Tang Nano 4K GW1NSR-4C  
**Data:** 13 de setembro de 2026

## 1. Resumo

O TP5 consolida o SAFE-FIELD como protótipo embarcado ARM64-FPGA. A imagem final foi sintetizada, roteada e temporizada no Gowin sem violações; cinco testes WASM passaram; a biblioteca/cliente Assembly passou nos ensaios nativos do Pi 4. FPGA↔Pi, operações numéricas, rejeição CRC, burst e estabilidade de 600 s foram verificados fisicamente.

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

Os testbenches cobrem Q1.15 positivo/negativo, limite e saturacao; FP16 normal, sinal, zero, overflow, NaN e underflow; CRC valido/invalido; OE/tri-state; e integracao top-level. O log WASM `docs_tp5/evidence/simulation/tp5_wasm_self_checking.log` registra cinco testes PASS. A sessão física confirmou PING + três operações e rejeição/recuperação CRC.

## 8. Desempenho e estabilidade

A instrumentação final usa `clock_gettime`/`perf_counter_ns` para RTT, sequence para perda, CRC/framing counters para integridade e logs com duração. O burst físico obteve 100/100, média 8,226915 ms, p95 11,895486 ms e 121,552 comandos/s. A rodada final de 600 s obteve 597/597 comandos e 791045 RAW24, sem perdas ou erros; RTT médio 1,747516 ms e p95 3,698757 ms. Dois coletores anteriores falharam por starvation instrumental Python (byte/CRC), preservados como histórico; a coleta chunked/C CRC passou sem alteração RTL.

## 9. Hardware externo e pinout

O TP5 preserva o pinout fisicamente validado no TP4: 27 MHz no pin 45; GPIO17 no 40; I2S SCK/WS/SD nos 41/42/43; LED no 10; UART FPGA->Pi no 39; UART Pi->FPGA no 46, com a camera desconectada. A programacao TP5 deve ser feita inicialmente em SRAM para rollback seguro.

## 10. Raspberry Pi Zero 2 W x Pi 4

O enunciado define Raspberry Pi Zero 2 W. A bancada disponivel utiliza Raspberry Pi 4 Model B. Ambos suportam AArch64 com Raspberry Pi OS 64-bit, portanto o codigo Assembly e o protocolo permanecem portaveis. A diferenca fisica de plataforma e declarada e nao e ocultada.

## 11. Evidencia fisica e limitacao atual

A imagem final foi programada em SRAM. No probe limpo, GPIO14/pino 8 chegou ao FPGA pin 46 (`rx_low_seen=true`), com 2650 RAW24, uma resposta válida, flags `0x94` e zero checksum/framing/I²S/overrun. Q15 e FP16 produziram os valores esperados. A evidência acústica INMP441 após reparo e o smoke RAW24 final também são PASS.

## 12. Integracao com o MVP SAFE-FIELD

O TP5 e o MVP compartilham o mesmo principio: FPGA para processamento deterministico e Raspberry para orquestracao. O TP5 nao usa estados QUIET/ACTIVE para interromper captura global de ocorrencia no MVP; a FSM de audio e um sinal/telemetria de segmentacao e observabilidade. A camada operacional completa continua preservando proveniencia e decisao humana.

## 13. Conclusao

A entrega TP5 tem os gates de software e hardware PASS, com evidências, fotos, PDF e ZIP auditados. Permanece pendente somente a gravação/upload do vídeo com operador; o link permanece `PENDENTE_LINK_FINAL`.
