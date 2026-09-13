# Roteiro de defesa - SAFE-FIELD TP5 - ate 5 minutos

**0:00-0:35 - abertura e arquitetura**  
Mostrar webcam + diagrama. Explicar que o TP5 consolida ARM64, Tang Nano 4K, I2S, transporte RAW24, protocolo de comandos, processamento numerico e telemetria. Mostrar a arquitetura bidirecional fisicamente verificada.

**0:35-1:25 - FPGA**  
Mostrar `verilog_tp5/rtl`: I2S, detector de energia/FSM, Q1.15, FP16, CRC, handshaking e telemetria. Mostrar waveform de `tb_arithmetic` e `tb_command_rx`.

**1:25-2:10 - Assembly ARM64**  
Mostrar `assembly_tp5/src`, biblioteca `.a`, Makefile e objdump. Executar `./build/tp5_demo` no Raspberry e destacar syscalls, parsing, buffers e protocolo.

**2:10-3:35 - integracao fisica**  
Mostrar Tang + Raspberry + microfone; executar PING + 3 operações, valores Q15/FP16 e rejeição/recuperação CRC. Mostrar smoke RAW24: 3966 frames/63456 amostras, CRC/perdas/frame errors 0.

**3:35-4:20 - estabilidade/desempenho**  
Mostrar burst 100/100 (121,552 comandos/s) e estabilidade 600 s (597/597, sem perdas/erros), além de P&R/STA com 0 violações setup/hold. Explicar brevemente as duas coletas históricas com starvation Python e a coleta final chunked/C CRC.

**4:20-5:00 - evolucao e conclusao**  
Explicar que o TP4 introduziu DSP/BSRAM/NEON e que o TP5 consolidou protocolo, bibliotecas Assembly, aritmética fixa/flutuante, telemetria, testes e documentação. Encerrar mostrando PDF/ZIP finais e `PENDENTE_LINK_FINAL` para o vídeo.
