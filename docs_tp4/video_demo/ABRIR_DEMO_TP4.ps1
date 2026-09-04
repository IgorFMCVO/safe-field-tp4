$ErrorActionPreference = 'Stop'

$files = @(
    '01_ARQUITETURA.png',
    '02_VERILOG_BRAM_DSP.png',
    '03_WAVEFORM.png',
    '04_ARM64_NEON.png',
    '05_BENCHMARK_NEON.png',
    '06_FPGA_PI_BIDIRECTIONAL.log',
    '07_AUDIO_PHYSICAL_PASS.png',
    '08_FINAL_RESULTS.md'
)

for ($index = 0; $index -lt $files.Count; $index++) {
    $path = Join-Path $PSScriptRoot $files[$index]
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Arquivo da demonstração não encontrado: $path"
    }
    Write-Host ("[{0}/8] {1}" -f ($index + 1), $files[$index]) -ForegroundColor Cyan
    Start-Process -FilePath $path
    if ($index -lt ($files.Count - 1)) {
        Read-Host 'Pressione ENTER para abrir a próxima tela'
    }
}

Write-Host 'Demonstração concluída.' -ForegroundColor Green
