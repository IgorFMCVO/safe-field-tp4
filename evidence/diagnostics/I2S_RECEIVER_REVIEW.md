# Revisão lógica do receptor I2S

Revisão executada em 03/09/2026 antes dos builds diagnósticos.

## Resultado

Nenhum erro lógico foi encontrado em `i2s_clock_gen.v` ou `i2s_rx_24.v`; esses
arquivos não foram alterados na branch de diagnóstico.

- SCK = 27 MHz / 10 = 2,700 MHz.
- WS = SCK / 64 = 42,1875 kHz, 32 clocks por slot.
- WS muda na borda de descida que antecede o índice 0.
- O índice 0 representa o atraso obrigatório de um clock do formato I2S.
- Os índices 1 a 24 deslocam MSB-first a palavra signed de 24 bits.
- `sample_valid` é emitido no índice 24 e o canal é preservado desde o índice 0.
- O receptor amostra SD um ciclo de 27 MHz depois da borda de subida gerada,
  dentro da fase alta de SCK e longe da troca de SD na borda de descida.

Os testes unitários existentes continuaram passando e o DEBUG 3 reconstruiu
exatamente a palavra 513, contando duas amostras zero e uma não-zero.

A primeira tentativa do testbench DEBUG 3 consultou os contadores no tempo zero
antes do POR e obteve `X`; o testbench foi corrigido para aguardar `reset_n`.
Isso foi um erro de teste, não do receptor, e o log da tentativa foi preservado.
