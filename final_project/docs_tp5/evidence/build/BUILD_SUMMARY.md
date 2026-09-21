# SAFE-FIELD TP5 — resumo verificável do build final

Data do build final: 2026-09-13  
Ferramenta: Gowin Designer Education V1.9.11.03 x64  
Dispositivo: GW1NSR-LV4CQN48PC6/I5 (Tang Nano 4K / GW1NSR-4C)  
Top: `safe_field_tp5_top`  

## Resultado

- Síntese: PASS.
- Place & Route: PASS.
- Bitstream: PASS.
- STA setup: PASS, 0 endpoints violados, slack mínimo 13,379 ns.
- STA hold: PASS, 0 endpoints violados, slack mínimo 0,558 ns.
- Fmax calculada: 42,268 MHz para requisito de 27,000 MHz.
- Bitstream: `verilog_tp5/build/safe_field_tp5_final/impl/pnr/safe_field_tp5_final.fs`.
- SHA-256 do bitstream: `2672D28A5C72F980C53447EC7B3DCF7A953828F6336A9B91ADE2DAAC478D2F18`.

## Utilização final

| Recurso | Uso | Utilização |
|---|---:|---:|
| Logic | 2169 / 4608 | 48% |
| Register | 2252 / 3573 | 64% |
| CLS | 2030 / 2304 | 89% |
| I/O Port | 8 / 39 | 21% |
| DSP | 1 / 8 | 13% |
| Clock PRIMARY | 1 / 8 | 13% |

## Warnings analisados

Foram emitidos 130 warnings no console final:

- 129 × `PA1001`: saídas/carry bits não usados após a poda das larguras efetivamente consumidas em `sf_raw24_i2s_rx_24`, `sf_command_rx` e nas primitivas DSP dos caminhos Q15/FP16. Não são erros funcionais; as saídas observadas estão cobertas pelos testbenches auto-verificáveis e o P&R terminou válido.
- 1 × `PR1014`: uso de recurso de roteamento genérico para o clock `sys_clk_d`. O relatório final, entretanto, contabiliza 1 recurso `PRIMARY`, 0 violações setup/hold e Fmax 42,268 MHz para 27 MHz. O mesmo aviso já existia em imagens validadas do projeto e não foi ocultado.

## Logs preservados

- `gowin_build_console.log`: primeira tentativa, falha de sintaxe preservada.
- `gowin_build_console_retry01.log`: primeira implementação válida, margem de timing ainda pequena.
- `gowin_build_console_retry02.log`: implementação após otimização do packetizer.
- `gowin_build_console_retry03.log`: build final usado para o hash acima.
- `jtag_scan_before_program.log`: detecção JTAG do GW1NSR-4C.
- `sram_program_final_retry01.log`: programação exclusivamente em SRAM da imagem final; nenhuma gravação em Flash.

Fonte primária de recursos e timing: relatórios Gowin em
`verilog_tp5/build/safe_field_tp5_final/impl/pnr/`.
