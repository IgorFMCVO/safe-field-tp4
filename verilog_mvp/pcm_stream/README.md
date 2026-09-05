# SAFE-FIELD MVP PCM stream

Variante independente do TP4 congelado. Ela preserva a aquisição I2S, o detector,
o override GPIO17 e o pinout físico validado, mas usa o TX já ligado (Tang 39 para
Raspberry GPIO15/pino físico 10) para PCM mono contínuo.

## Decisão de largura de banda

- Fonte: 42.187,5 samples/s LEFT.
- PCM: signed 16-bit little-endian, obtido por `sample_data[23:8]`.
- Dados crus: 84.375 bytes/s.
- Protocolo: 78 bytes para 32 samples, ou 1.028.320,3125 bit/s incluindo 8-N-1.
- UART anterior a 115.200 bit/s: **inviável** (89,26% acima até da capacidade
  teórica de payload e 8,93 vezes abaixo do requisito protocolado).
- UART escolhida: 1.500.000 bit/s exatos (`27 MHz / 18`), utilização 68,55% e
  margem serial 31,45%.

O `.wav` no Raspberry usa 42.188 Hz no cabeçalho porque RIFF/WAVE aceita taxa
inteira; o sidecar JSON registra a taxa física exata 42.187,5 Hz.

## Protocolo

Frame fixo de 78 bytes: `A5 C3`, versão, tipo, sequência, contador da primeira
amostra, contagem, flags, 32 amostras PCM16 LE e CRC-16/CCITT-FALSE. Sequência,
contador e CRC permitem medir perda, descarte e corrupção separadamente.
Os flags são: bit 0 erro de frame I2S, bit 1 overrun, bit 2 UART reversa observada
LOW e bit 3 GPIO17 HIGH.

## Segurança e build

O script de build contém gates de pinout antes de invocar o Gowin. Ele gera apenas
`build/mvp_pcm_stream/`; não escreve nos builds TP4.

```powershell
node .\verilog_mvp\pcm_stream\sim\run_pcm_stream.mjs
& 'C:\Gowin\Gowin_V1.9.12.03_x64\IDE\bin\gw_sh.exe' `
  .\verilog_mvp\pcm_stream\scripts\build_mvp_pcm_stream.tcl
```

Não programe automaticamente. O primeiro teste físico futuro deve ser SRAM apenas,
Raspberry configurada a 1.500.000 baud, seguida de captura curta e verificação de
CRC/perdas antes de qualquer uso no pipeline operacional.
