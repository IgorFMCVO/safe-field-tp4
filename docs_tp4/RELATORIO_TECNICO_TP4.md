# SAFE-FIELD — Relatório Técnico TP4

**Aluno:** Igor de Freitas Monteiro  
**Disciplina:** Sistemas Digitais Embarcados  
**Plataformas reais:** Tang Nano 4K GW1NSR-4C e Raspberry Pi 4 Model B  
**Data:** 04/09/2026

## 1. Introdução

O SAFE-FIELD demonstra aquisição e processamento determinístico de áudio em
FPGA, integração com processador ARM64 e comunicação serial verificável. O
trabalho parte de uma baseline física Raspberry GPIO17 -> Tang -> LED e evolui
até a cadeia som -> INMP441 -> I2S -> FPGA -> energia/FSM -> UART -> Raspberry.

O fechamento acadêmico acrescenta, sem modificar a baseline, uma unidade
aritmética mapeada em DSP, buffer funcional em BSRAM, comandos Pi->Tang com CRC,
Assembly AArch64 e rotinas NEON inteiras e floating point.

## 2. Evolução TP3 -> TP4

A integração GPIO17 validada permanece ativa como override. O TP4 acrescenta:

- I2S master a partir de 27 MHz;
- reconstrução LEFT signed de 24 bits;
- energia, média, histerese e FSM;
- telemetria FPGA->Pi com sequence e CRC;
- potência `sample[23:8]^2` em DSP dedicado;
- BSRAM de 256 valores e média de potência;
- protocolo numérico Pi->FPGA;
- competências ARM64 e NEON mensuradas no Pi 4.

## 3. Arquitetura

O diagrama completo está em `ARQUITETURA_TP4.md`. O caminho crítico permanece
no FPGA. O Raspberry valida, registra e publica eventos; não substitui a decisão
determinística da Tang. A câmera UVC e o wearable são módulos preparados, porém
fora do núcleo avaliado. Transcrição, IA e PCM completo foram congelados.

## 4. Hardware e pinout

| Sinal | Tang package pin | Direção | Elétrica |
|---|---:|---|---|
| clock 27 MHz | 45 | entrada | LVCMOS33 |
| GPIO17 | 40 | Pi -> Tang | LVCMOS33 |
| I2S SCK | 41 | Tang -> INMP441 | LVCMOS33 |
| I2S WS | 42 | Tang -> INMP441 | LVCMOS33 |
| I2S SD | 43 | INMP441 -> Tang | LVCMOS33 |
| LED | 10 | saída | LVCMOS18 |
| UART TX | 39 | Tang -> Pi GPIO15 | LVCMOS33 |
| UART RX acadêmico | 46 | Pi GPIO14 -> Tang | LVCMOS33, input |

O pin 46 foi selecionado pelo esquemático Sipeed 3603: `IOT13B`, Bank 1 a
3,3 V, net `CAMERA_SDA`. Seu uso exige câmera desconectada. A ligação física
Pi GPIO14/TXD -> Tang pin 46 foi executada com as placas desenergizadas e o
build acadêmico corrigido foi programado exclusivamente em SRAM.

## 5. Áudio físico

Após correção dos contatos dos pins 41 e 43, SD voltou a transmitir e o
diagnóstico anterior de INMP441 defeituoso foi invalidado. As evidências reais
mostram:

| Métrica | Resultado |
|---|---:|
| samples LEFT não-zero | 1024/1024 no gate pós-reparo |
| voz / silêncio RMS | 4,992566x |
| voz / silêncio mean absolute | 4,372595x |
| palmas | três eventos distinguíveis |
| frame errors | 0 |
| aquisição contínua | 99,42 s |

## 6. Unidade aritmética e DSP

`safe_field_audio_energy_dsp` reduz o sample signed de 24 para 16 bits por
seleção dos bits mais significativos e calcula seu quadrado em pipeline. Foram
testados zero, positivo, negativo, máximo positivo e mínimo negativo. O limite
`-32768^2=1073741824` cabe em 32 bits sem saturação.

O synthesis hierarchy report mostra DSP=1 em `power_dsp`; o relatório P&R
mostra `MULT18X18=1`. O algoritmo aplicado a 8.192 samples físicos produziu
potência média 245,4473 no silêncio e 6117,9492 na voz, razão 24,9257x, sem
overflow.

## 7. BSRAM e média

`safe_field_energy_bram` implementa 256 x 32 bits, escrita de uma potência por
sample LEFT e leitura síncrona. Um acumulador de 40 bits calcula média a cada
256 amostras. O testbench verificou endereços 0, 123 e 255, wrap e média de
0..255 igual a 127. O relatório mostra `SDPB=1`, independente de GAO.

## 8. UART bidirecional, checksum e telemetria

A direção Tang->Pi v1 já foi fisicamente aprovada: 3.264 mensagens válidas,
zero perdas de sequência, zero erros de avanço de frame e uma transição física
QUIET->ACTIVE->QUIET.

O novo frame Pi->Tang tem sync `A6 6A`, versão, comando, sequence, payload32 e
CRC-8/ATM. Três vetores square16 passaram e um CRC corrompido foi rejeitado. A
resposta reutiliza o TX aprovado com flag de response. No ensaio físico, os
operandos `123`, `-123` e `32767` produziram respectivamente `15129`, `15129` e
`1073676289`, todos idênticos ao esperado, com zero erro de checksum e zero
perda de sequência. A revisão física também encontrou uma condição de handshake
na arbitragem da telemetria: `valid` podia ser removido antes de `ready`. O sinal
passou a permanecer ativo até o handshake efetivo, eliminando a perda da terceira
resposta sem modificar o caminho de áudio, DSP ou BSRAM.

## 9. Assembly AArch64

O código foi compilado e executado no Raspberry Pi 4 real com GCC 14.2.0. A
adição 128-bit usa `ADDS/ADC`; a conversão usa `SCVTF`; a LUT trata estados; o
mix do protocolo usa máscara, shift, XOR e `ROR`. Todos os valores expected x
actual foram idênticos. O `objdump -d -S` está preservado.

## 10. NEON inteiro e floating point

A energia inteira escalar usa `SMULL`; a versão NEON usa 8 lanes com
`SMULL/SMULL2/UADALP`. O resultado foi exatamente 21865754704 em ambas. A
normalização float multiplica por 0,625; a versão NEON opera 4 floats por vetor,
com erro máximo zero para tolerância 1e-7.

No run de 800 repetições, o speedup foi 3,273697x inteiro e 1,126641x float.
Runs adicionais mostram variação, preservada sem selecionar apenas o melhor
caso.

## 11. Simulação e waveforms

Quatro testbenches auto-verificáveis totalizaram 40 checks:

- DSP: 10;
- BSRAM: 5;
- UART/CRC: 8;
- integração I2S/DSP/BRAM/UART/GPIO17: 17.

Todos terminaram `TEST_RESULT: PASS`. Foram exportados quatro VCDs e renderizados
PNGs do DSP expected/actual e dos comandos UART/erro de checksum.

## 12. Síntese, P&R e STA

| Item | Resultado |
|---|---:|
| Logic | 1065/4608, 24% |
| Registers | 833/3573, 24% |
| CLS | 827/2304, 36% |
| BSRAM | 1/10; SDPB=1 |
| DSP | MULT18X18=1 |
| endpoints setup/hold violados | 0/0 |
| Fmax | 38,297 MHz |
| requisito | 27 MHz |

O build bidirecional corrigido gerou `.fs` com SHA-256
`6E4C460162816C54EE38B11CDA246004C05FE07CEC4C1FA963FDBB36092E172F`.
O build acadêmico anterior foi preservado, sem sobrescrita.

## 13. Warnings

Os 56 warnings foram preservados: 1 `NL0002`, 54 `PA1001` de saídas
carry/cascade não usadas e 1 `PR1014` sobre rota genérica do clock. O STA passou
com margem e nenhum warning foi mascarado.

## 14. Desempenho e latência

O DSP tem um ciclo registrado (37,037 ns) e throughput teórico de uma operação
por ciclo. A BSRAM lê em um ciclo; a janela de 256 samples dura 6,068 ms. Um
frame UART de telemetria usa 1,387 ms e o comando de 11 bytes 0,953 ms. A tabela
completa inclui os benchmarks ARM64 em `DESEMPENHO_LATENCIA_TP4.md`.

## 15. SAFE-FIELD Core e módulos futuros

O Core Raspberry passou 6/6 testes e ingeriu 624 eventos FPGA em teste físico.
O scaffold UVC retorna `CAMERA_NOT_CONNECTED` sem fabricar JPEG. A API wearable
HTTP publica estados do FPGA. Camera física, wearable físico, IA, transcrição e
PCM integral permanecem explicitamente fora do fechamento.

## 16. Limitações

- a última iteração de estabilidade FSM tem regressão sobre dados físicos, mas
  não uma nova recaptura GAO;
- o PDF separado do enunciado e o relatório TP3 não estavam no workspace.

## 17. Conclusão

Foram atendidos 22 dos 22 itens: 22 PASS, zero PARTIAL e zero MISSING. DSP e BRAM
são recursos reais comprovados pela síntese, ARM64/NEON foi executado no Pi 4 e
as duas direções UART foram fisicamente aceitas. O vídeo foi gravado e publicado
em https://youtu.be/1Ancm5QdG2E. O link final do Google Drive é apenas uma
providência de submissão do operador.

## Referências

1. Sipeed, Tang Nano 4K schematic 3603:
   <https://dl.sipeed.com/fileList/TANG/Nano%204K/HDK/02_Schematic/Tang_Nano_4K_3603_Schematic_.pdf>
2. GOWIN Semiconductor, GowinSynthesis User Guide, SUG550:
   <https://cdn.gowinsemi.com.cn/SUG550E.pdf>
3. TDK InvenSense, INMP441 datasheet:
   <https://invensense.tdk.com/wp-content/uploads/2015/02/INMP441.pdf>
4. Arm, A64 instruction set architecture documentation:
   <https://developer.arm.com/architectures/instruction-sets/a-profile>
