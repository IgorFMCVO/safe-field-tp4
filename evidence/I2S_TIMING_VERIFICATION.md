# Verificação de timing I2S — RTL e pós-P&R

Data: 03/09/2026. Clock de entrada restringido e analisado: 27,000 MHz.

## Razões de divisão implementadas

`i2s_clock_gen.v` usa `HALF_PERIOD_CLKS=5` e `SLOT_BITS=32`:

- período de `sys_clk`: 1 / 27 MHz = 37,037 ns;
- nível HIGH e LOW de SCK: 5 ciclos = 185,185 ns;
- período SCK: 10 ciclos = 370,370 ns;
- SCK: 27 MHz / 10 = 2,700 MHz;
- frame: 64 SCK (32 por slot LEFT/RIGHT);
- WS: 2,700 MHz / 64 = 42,1875 kHz.

A simulação final mede 5 ciclos por meio período SCK, 32 períodos por meio
frame WS e 64 por frame completo. Todos os valores esperado/obtido passaram.
P&R não cria um novo domínio: SCK/WS são saídas registradas do domínio de
27 MHz, portanto as razões inteiras permanecem as mesmas no circuito mapeado.

## Comparação com o datasheet INMP441 rev. 1.1

| Parâmetro | Limite INMP441 | Implementado | Resultado |
|---|---:|---:|---|
| frequência SCK | 0,5 a 3,2 MHz | 2,700 MHz | PASS |
| período SCK | mínimo 312 ns | 370,370 ns | PASS |
| SCK HIGH | mínimo 50 ns | 185,185 ns | PASS |
| SCK LOW | mínimo 50 ns | 185,185 ns | PASS |
| frequência WS | 7,8 a 50 kHz | 42,1875 kHz | PASS |
| clocks por frame | exatamente 64 | 64 | PASS |
| clocks por slot | exatamente 32 | 32 | PASS |
| palavra | I2S, 24-bit, complemento de dois, MSB-first | igual | PASS |
| atraso do MSB | 1 SCK após início do half-frame | índice 1 | PASS |

WS troca na borda de descida anterior ao bit de atraso. SD é amostrado um ciclo
de 27 MHz depois da borda de subida SCK observada pelo gerador, dentro do nível
HIGH. Desde a borda de descida anterior, o dado dispõe de aproximadamente
222,222 ns até a captura lógica.

## STA final

- modelo setup: Slow 1,14 V, 85 C, C6/I5;
- modelo hold: Fast 1,26 V, 0 C, C6/I5;
- 419 caminhos / 416 endpoints;
- violações setup: 0; violações hold: 0; TNS setup/hold: 0;
- WNS setup: +3,075 ns; pior hold: +0,708 ns;
- Fmax estimada: 29,444 MHz para restrição de 27,000 MHz.

O STA é interno. O datasheet não fornece no quadro de timing um atraso máximo
de SD após SCK; a margem de captura externa é, portanto, verificada pela fase do
protocolo e deve ser confirmada com osciloscópio/analisador lógico no primeiro
ensaio físico.

Fonte primária:
<https://invensense.tdk.com/wp-content/uploads/2015/02/INMP441.pdf>
