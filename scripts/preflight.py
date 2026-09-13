#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[1]
required=['verilog_tp5/rtl/safe_field_tp5_top.v','verilog_tp5/rtl/sf_fixed_q15_mac.v','verilog_tp5/rtl/sf_fp16_mul.v','verilog_tp5/tb/tb_arithmetic.v','verilog_tp5/tb/tb_command_rx.v','verilog_tp5/tb/tb_tp5_integration.v','assembly_tp5/Makefile','assembly_tp5/src/main.S','assembly_tp5/src/protocol.S','assembly_tp5/src/uart_client.S','assembly_tp5/run_on_pi.sh','assembly_tp5/tests/uart_performance.py','docs_tp5/RELATORIO_TECNICO_TP5.md','docs_tp5/ROTEIRO_VIDEO_TP5_5MIN.md','docs_tp5/MATRIZ_RUBRICA_TP5.md','.github/workflows/validate-tp5.yml']
missing=[p for p in required if not (root/p).is_file()]
if missing: print('MISSING',*missing,sep='\n');sys.exit(1)
text=(root/'verilog_tp5/rtl/safe_field_tp5_top.v').read_text()
for token in ['sf_command_rx','sf_telemetry_tx','sf_fixed_q15_mac','sf_fp16_mul','audio_energy_detector']: assert token in text,token
asm='\n'.join((root/p).read_text() for p in ['assembly_tp5/src/io_syscalls.S','assembly_tp5/src/parse.S','assembly_tp5/src/protocol.S'])
for token in ['svc #0','sf_ascii_to_u64','sf_u64_to_ascii','sf_crc8_atm']: assert token in asm,token
assert 'libsafe_field_tp5.a' in (root/'assembly_tp5/Makefile').read_text()
print('TP5 local preflight: PASS')
