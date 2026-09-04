# Verilog TP4 SAFE-FIELD

Snapshot acadêmico independente da baseline física validada.

## Conteúdo

- `rtl/`: top acadêmico, DSP, BSRAM, UART RX/comandos e cópia explícita das
  dependências congeladas;
- `tb/`: quatro testbenches auto-verificáveis, total de 40 checks;
- `constraints/`: pinout e clock de 27 MHz;
- `scripts/`: simulação, build Gowin, replay físico e renderização de VCD;
- `build/`: relatórios de síntese, P&R, STA e bitstream acadêmico;
- `evidence/`: logs, VCDs, PNGs e análise sobre samples físicos reais;
- `bitstreams/`: baseline validada e variante acadêmica, sem sobrescrita.

## Reproduzir

Na raiz do projeto:

```powershell
node verilog_tp4/scripts/run-official-rubric.mjs
& 'C:\Gowin\Gowin_V1.9.11.03_x64\IDE\bin\gw_sh.exe' `
  verilog_tp4/scripts/build_safe_field_tp4_official_bidirectional.tcl
```

O build bidirecional corrigido foi programado somente em SRAM depois da ligação
Pi GPIO14/TXD para Tang package pin 46 ser feita com as placas desenergizadas e
confirmada pelo operador. O teste físico terminou 3/3 PASS, com zero erro de
checksum e zero perda de sequência.
