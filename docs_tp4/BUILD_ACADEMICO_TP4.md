# Build acadêmico Gowin

## Resultado

- simulação: PASS, 40/40 checks;
- síntese: PASS;
- P&R: PASS;
- STA: PASS;
- endpoints setup/hold violados: 0/0;
- Fmax: 37,778 MHz para 27 MHz;
- bitstream: `safe_field_tp4_official.fs`;
- SHA-256: `0460826C112FFF69A83E6420BDD28657AE5265EFD5E7D96BE457B9CBA1581A73`;
- programação física: **não executada**.

## Recursos finais

| Recurso | Uso |
|---|---:|
| Logic | 1068/4608 (24%) |
| Register | 833/3573 (24%) |
| CLS | 823/2304 (36%) |
| I/O | 8/39 (21%) |
| BSRAM | **1/10; SDPB=1** |
| DSP | **MULT18X18=1**; relatório agregado 0,5/8 macro |

O hierarchy synthesis report atribui DSP=1 a `power_dsp` e BSRAM=1 a
`energy_buffer`. A memória não pertence ao GAO.

## Áudio físico reaproveitado

O algoritmo sintetizado foi aplicado a duas capturas GAO físicas de 8.192
samples cada. Potência média 16-bit reduzida: silêncio 245,4473; voz
6.117,9492; razão voz/silêncio 24,9257x; RMS equivalente 4,9926x; overflow 0.
Resultado: PASS.
