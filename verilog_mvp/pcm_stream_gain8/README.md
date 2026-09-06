# SAFE-FIELD MVP PCM stream gain8

Variante aditiva do transporte PCM, criada sem modificar o TP4 congelado nem o
build/bitstream `mvp_pcm_stream` já validado. O pinout e o protocolo UART
`UART_PCM16_V1` permanecem idênticos.

## Conversão 24 → 16 bits

O caminho original transmite `sample_data[23:8]`, equivalente a `sample >>> 8`.
Esta variante aplica:

```text
scaled = signed_sample_24 >>> 5
pcm16  = clamp(scaled, -32768, +32767)
```

O deslocamento 5 preserva três bits adicionais e representa ganho digital 8×
em relação ao caminho `[23:8]`. A saturação explícita impede wraparound nos
dois sinais. Um wrapper converte e entrega `{pcm16, 8'b0}` ao transmissor
original, portanto sync, versão, tipo, sequência, contador, flags, 32 samples,
CRC e UART 1,5 Mbaud não mudam.

## Build separado

```powershell
node .\verilog_mvp\pcm_stream_gain8\sim\run_pcm_stream_gain8.mjs
& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gw_sh.exe' `
  .\verilog_mvp\pcm_stream_gain8\scripts\build_mvp_pcm_stream_gain8.tcl
```

Saída:

```text
build/mvp_pcm_stream_gain8/impl/pnr/safe_field_mvp_pcm_stream_gain8.fs
```

O script tem gates para o device GW1NSR-4C, diretório de build separado e o
pinout 40/41/42/43/45/10/39/46. Ele não chama o Gowin Programmer. Programação
em SRAM não foi executada nesta etapa.

