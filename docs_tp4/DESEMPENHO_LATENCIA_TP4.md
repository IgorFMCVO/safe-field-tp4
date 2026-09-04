# Desempenho e latência SAFE-FIELD TP4

| Módulo | Clock/taxa | Ciclos | Latência/tempo medido | Throughput | Observação |
|---|---:|---:|---:|---:|---|
| I2S LEFT | WS 42,1875 kHz | 64 SCK/frame | 23,704 µs/frame | 42.187,5 samples/s | `frame_errors=0` físico |
| DSP `MULT18X18` | 27 MHz | 1 pipeline | 37,037 ns | até 27 Mresultados/s | 1 instância; 16-bit signed square |
| BSRAM `SDPB` | 27 MHz | 1 leitura síncrona | 37,037 ns | 1 read + 1 write/ciclo | 256 x 32 bits, uma BSRAM |
| média de potência | 42,1875 ksample/s | 256 samples | 6,068 ms/janela | 164,795 janelas/s | acumulador 40 bits |
| UART FPGA->Pi | 115.384,6 baud real | 160 bits/frame | 1,387 ms/frame | 720,9 frames/s máx. | telemetria real 164,8 frames/s |
| UART Pi->FPGA | 115.384,6 baud real | 110 bits/comando | 0,953 ms/comando | 1.048 comandos/s máx. | CRC e sequence |
| ARM64 energia escalar | CPU Pi 4 variável | 65.536 x 800 | 58.673.389 ns | 893,6 Melem/s | execução real, DVFS ativo |
| NEON energia inteira | CPU Pi 4 variável | 8 elementos/vetor | 17.922.667 ns | 2.925,3 Melem/s | speedup 3,273697x no run 800 |
| ARM64 float escalar | CPU Pi 4 variável | 65.536 x 800 | 59.432.019 ns | 882,0 Melem/s | escala 0,625 |
| NEON float | CPU Pi 4 variável | 4 elementos/vetor | 52.751.518 ns | 993,9 Melem/s | speedup 1,126641x no run 800 |

Os benchmarks adicionais de 50/200/800 repetições foram preservados sem
normalização artificial. O speedup inteiro observado variou de 3,243166x a
9,566309x e o float de 1,126641x a 2,052943x; a variação é compatível com
DVFS/caches/sistema operacional e não foi ocultada.

O STA Gowin analisou 2.472 paths e 2.473 endpoints: setup/hold violados 0/0,
TNS 0/0, Fmax 37,778 MHz para requisito 27 MHz.
