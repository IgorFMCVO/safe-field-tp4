# Roteiro de defesa - SAFE-FIELD TP5 - ate 5 minutos

**0:00-0:35 - abertura e arquitetura**  
Mostrar webcam + diagrama. Explicar que o TP5 consolida ARM64, Tang Nano 4K, I2S, UART bidirecional, processamento numerico e telemetria.

**0:35-1:25 - FPGA**  
Mostrar `verilog_tp5/rtl`: I2S, detector de energia/FSM, Q1.15, FP16, CRC, handshaking e telemetria. Mostrar waveform de `tb_arithmetic` e `tb_command_rx`.

**1:25-2:10 - Assembly ARM64**  
Mostrar `assembly_tp5/src`, biblioteca `.a`, Makefile e objdump. Executar `./build/tp5_demo` no Raspberry e destacar syscalls, parsing, buffers e protocolo.

**2:10-3:35 - integracao fisica**  
Mostrar Tang + Raspberry + microfone. Executar PING e um vetor Q15/FP16. Mostrar resposta com mesma sequence e CRC correto. Em seguida falar proximo ao microfone e mostrar energia/estado mudando.

**3:35-4:20 - estabilidade/desempenho**  
Mostrar log de 10 minutos: total de frames, perdas, CRC/framing errors, RTT medio/p95 e throughput. Nao esconder warnings/erros.

**4:20-5:00 - evolucao e conclusao**  
Explicar que o TP4 introduziu DSP/BSRAM/NEON e UART bidirecional; o TP5 consolidou protocolo final, bibliotecas Assembly, aritmetica fixa/flutuante, telemetria, testes e documentacao. Encerrar com limitacoes reais e proximos passos do MVP.
