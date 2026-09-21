$ErrorActionPreference = 'Stop'
$demo = Split-Path -Parent $MyInvocation.MyCommand.Path
$docs = Split-Path -Parent $demo
$root = Split-Path -Parent $docs

$targets = @(
    (Join-Path $demo '01_ARQUITETURA_FINAL.png'),
    (Join-Path $docs 'ARQUITETURA_FINAL_TP5.md'),
    (Join-Path $root 'verilog_tp5\rtl\safe_field_tp5_top.v'),
    (Join-Path $root 'verilog_tp5\rtl\sf_fixed_q15_mac.v'),
    (Join-Path $root 'verilog_tp5\rtl\sf_fp16_mul.v'),
    (Join-Path $docs 'evidence\build\BUILD_SUMMARY.md'),
    (Join-Path $docs 'evidence\simulation\tp5_wasm_self_checking.log'),
    (Join-Path $demo '03_WAVEFORM_RAW24_COMMAND.png'),
    (Join-Path $docs 'evidence\simulation\waveforms\tb_tp5_raw24_coexist.vcd'),
    (Join-Path $root 'assembly_tp5\src\uart_client.S'),
    (Join-Path $root 'assembly_tp5\evidence\raspberry_native\native_build_test_retry03.log'),
    (Join-Path $root 'assembly_tp5\evidence\raspberry_native\physical_uart_roundtrip_final.log'),
    (Join-Path $root 'assembly_tp5\evidence\raspberry_native\tp5_uart_perf_final.json'),
    (Join-Path $root 'assembly_tp5\evidence\raspberry_native\tp5_uart_stability_600s_retry02.json'),
    (Join-Path $docs 'evidence\audio\INMP441_ACOUSTIC_REVALIDATION_20260913.md'),
    (Join-Path $docs 'output\pdf\RELATORIO_TECNICO_SAFE_FIELD_TP5.pdf'),
    (Join-Path $demo 'RESULTADOS_FINAIS.md')
)

foreach ($target in $targets) {
    if (Test-Path -LiteralPath $target) {
        Start-Process -FilePath $target
        Start-Sleep -Milliseconds 650
    } else {
        Write-Warning "Ainda não disponível: $target"
    }
}
