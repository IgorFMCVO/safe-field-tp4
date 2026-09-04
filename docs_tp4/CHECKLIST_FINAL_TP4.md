# Checklist final SAFE-FIELD TP4

## Engenharia

- [x] branch `tp4-official-rubric-closeout` criada de `a6342e5`;
- [x] baselines e bitstreams anteriores preservados;
- [x] RTL acadêmico separado;
- [x] DSP signed square integrado ao áudio;
- [x] BSRAM funcional 256 x 32 integrada;
- [x] `MULT18X18=1` e `SDPB=1` comprovados em relatório;
- [x] 40/40 checks de simulação;
- [x] VCD e PNG de waveform;
- [x] síntese, P&R e STA PASS;
- [x] 56 warnings classificados, nenhum ocultado;
- [x] `.fs` acadêmico corrigido separado, programado somente em SRAM;
- [x] UART RX pin 46 documentado e constrained como input;
- [x] CRC-8/ATM e três vetores Pi->Tang simulados;
- [x] FPGA->Pi físico PASS preservado.

## ARM64

- [x] operação 128-bit;
- [x] inteiro->double;
- [x] lookup table;
- [x] masks, shifts, XOR e rotate;
- [x] NEON inteiro e escalar equivalentes;
- [x] NEON float e escalar equivalentes;
- [x] benchmark 50/200/800 no Raspberry Pi 4 real;
- [x] build, execução, `objdump` e binário ARM64 preservados.

## Entrega

- [x] estrutura `/verilog_tp4`, `/assembly_tp4`, `/docs_tp4`;
- [x] relatório Markdown e PDF real;
- [x] manifesto, matriz, checklist, links e hashes;
- [x] ZIP acadêmico novo, sem substituir ZIP de engenharia;
- [x] branch final commitada e tag local preparada;
- [x] ARM->FPGA físico: 3/3 comandos, CRC=0 e perdas=0;
- [x] vídeo gravado e registrado no YouTube;
- [x] GitHub público acadêmico publicado e tag final registrada.
