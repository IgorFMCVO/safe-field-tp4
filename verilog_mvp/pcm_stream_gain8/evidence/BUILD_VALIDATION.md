# MVP PCM stream gain8 — validação de build

Build concluído em 06/09/2026 com Gowin V1.9.11.03 Education para
`GW1NSR-LV4CQN48PC6/I5` (`GW1NSR-4C`). Esta é uma variante aditiva; nenhum RTL
do TP4 ou de `verilog_mvp/pcm_stream` foi alterado.

## Resultado

| Gate | Resultado | Evidência |
|---|---|---|
| Conversão signed 24→16 | PASS | `simulation.log`: `>>>5`, positivos, negativos, limites e saturação |
| Protocolo UART | PASS | header/tipo/flags, payload gain8, LEFT-only e CRC |
| Vazão física | PASS | 320 samples, 10 pacotes, divisor 18, zero drop/overrun |
| Síntese | PASS | 0 warnings, 0 errors |
| Place & Route | PASS | `Placement and routing completed` |
| STA | PASS | 0 setup violations, 0 hold violations, TNS setup/hold 0 |
| Bitstream separado | PASS | caminho e SHA-256 abaixo |
| Programação física | NÃO EXECUTADA | nenhuma chamada ao Programmer; Flash e SRAM intocadas |

## Conversão verificada

- caminho original preservado: `sample[23:8]` (`>>>8`);
- variante: deslocamento aritmético `>>>5`, ganho relativo 8×;
- faixa linear final: `-1048576..1048575` na entrada de 24 bits;
- acima da faixa: satura em `+32767`;
- abaixo da faixa: satura em `-32768`;
- nenhum wraparound positivo/negativo.

## Timing e utilização

- clock requerido: 27,000 MHz (37,037 ns);
- Fmax alcançado: 37,342 MHz;
- pior slack de setup: +10,258 ns;
- pior slack de hold: +0,566 ns;
- endpoints violados setup/hold: 0/0;
- TNS setup/hold: 0,000/0,000;
- logic: 1430/4608 (32%);
- registers: 1502/3573 (43%);
- CLS: 1699/2304 (74%);
- I/O: 8/39 (21%).

## Warnings revisados (7)

1. Seis `PA1001` (`n7_1_SUM` a `n12_1_SUM`) pertencem ao receptor
   `i2s_rx_24` congelado e indicam carry intermediário sem consumidor após
   otimização. São os mesmos seis warnings do build PCM fisicamente validado;
   não envolvem o novo conversor ou o protocolo.
2. Um `PR1014` registra routing genérico de `sys_clk_d`. Também já existia no
   build validado. O clock segue explicitamente constrangido, com Fmax
   37,342 MHz para requisito 27 MHz e zero violações de setup/hold.

Não houve warning de truncamento signed, latch, pinout, porta sem constraint,
conflito de banco ou saturação.

## Pinout final preservado

| Sinal | Pin | Direção/tipo |
|---|---:|---|
| `sys_clk` | 45 | input LVCMOS33 |
| `pi_signal` | 40 | input LVCMOS33 |
| `i2s_sck` | 41 | output LVCMOS33 |
| `i2s_ws` | 42 | output LVCMOS33 |
| `i2s_sd` | 43 | input LVCMOS33 pull-down |
| `uart_tx` | 39 | output LVCMOS33 |
| `uart_rx` | 46 | input LVCMOS33 pull-up |
| `led` | 10 | output LVCMOS18 |

## Bitstreams e preservação

Novo arquivo:

```text
C:\SAFE-FIELD\fpga\tp4-audio-inmp441\build\mvp_pcm_stream_gain8\impl\pnr\safe_field_mvp_pcm_stream_gain8.fs
SHA-256: 9941D50499C18C943BA9E4EEE6857677EB51084D0B91C2D08A816FEC7C93D70E
size: 1168345 bytes
```

Bitstream validado anterior, confirmado inalterado após o build:

```text
C:\SAFE-FIELD\fpga\tp4-audio-inmp441\build\mvp_pcm_stream\impl\pnr\safe_field_mvp_pcm_stream.fs
SHA-256: F46314D4A3478B6157A5253DF07E2AAB2022D305EA16E94E0F9F9A8706C0EC7B
```

## Comandos executados

```powershell
node .\verilog_mvp\pcm_stream_gain8\sim\run_pcm_stream_gain8.mjs

& 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gw_sh.exe' `
  '.\verilog_mvp\pcm_stream_gain8\scripts\build_mvp_pcm_stream_gain8.tcl' `
  2>&1 | Tee-Object `
  '.\verilog_mvp\pcm_stream_gain8\evidence\gowin_build_console.log'

Get-FileHash `
  .\build\mvp_pcm_stream_gain8\impl\pnr\safe_field_mvp_pcm_stream_gain8.fs `
  -Algorithm SHA256
```

Logs completos permanecem em `evidence/` e em
`build/mvp_pcm_stream_gain8/impl/{gwsynthesis,pnr}/`.

