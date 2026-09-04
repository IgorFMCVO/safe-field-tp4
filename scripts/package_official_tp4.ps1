param([switch]$ReplaceExisting)

$ErrorActionPreference = 'Stop'

$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if ($repo -ne 'C:\SAFE-FIELD\fpga\tp4-audio-inmp441') {
    throw "Unexpected repository path: $repo"
}

$deliveryRoot = 'C:\SAFE-FIELD\TP4_ACADEMIC_FINAL'
$packageRoot = Join-Path $deliveryRoot 'Igor_Monteiro_PB_TP4'
$zipPath = 'C:\SAFE-FIELD\Igor_Monteiro_PB_TP4.ZIP'

if ((Test-Path -LiteralPath $packageRoot) -or (Test-Path -LiteralPath $zipPath)) {
    if (-not $ReplaceExisting) {
        throw 'Academic delivery target already exists; use -ReplaceExisting after preserving the prior ZIP.'
    }
    if ($packageRoot -ne 'C:\SAFE-FIELD\TP4_ACADEMIC_FINAL\Igor_Monteiro_PB_TP4' -or
        $zipPath -ne 'C:\SAFE-FIELD\Igor_Monteiro_PB_TP4.ZIP') {
        throw 'Refusing to replace unexpected paths.'
    }
    if (Test-Path -LiteralPath $packageRoot) {
        Remove-Item -LiteralPath $packageRoot -Recurse -Force
    }
    if (Test-Path -LiteralPath $zipPath) {
        Remove-Item -LiteralPath $zipPath -Force
    }
}

New-Item -ItemType Directory -Force -Path $deliveryRoot, $packageRoot | Out-Null

function Copy-TreeFiltered {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )

    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    $sourceRoot = (Resolve-Path -LiteralPath $Source).Path
    $files = Get-ChildItem -LiteralPath $sourceRoot -File -Recurse -Force | Where-Object {
        $_.FullName -notmatch '[\\/](\.git|__pycache__|\.pytest_cache|\.mypy_cache|\.cache|node_modules|tmp|pre_handshake_fix_waveforms)[\\/]' -and
        $_.Extension -notin @('.pyc', '.pyo', '.tmp', '.vcd', '.db', '.bin', '.binx', '.vg') -and
        $_.Name -notmatch '\.tar\.gz$'
    }
    foreach ($file in $files) {
        $relative = $file.FullName.Substring($sourceRoot.Length).TrimStart('\')
        $target = Join-Path $Destination $relative
        $targetDir = Split-Path -Parent $target
        New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
        Copy-Item -LiteralPath $file.FullName -Destination $target -Force
    }
}

Copy-TreeFiltered -Source (Join-Path $repo 'verilog_tp4') -Destination (Join-Path $packageRoot 'verilog_tp4')
Copy-TreeFiltered -Source (Join-Path $repo 'assembly_tp4') -Destination (Join-Path $packageRoot 'assembly_tp4')
Copy-TreeFiltered -Source (Join-Path $repo 'docs_tp4') -Destination (Join-Path $packageRoot 'docs_tp4')

$rootFiles = @(
    'CHECKLIST_FINAL_TP4.md',
    'LINKS_ENTREGA_TP4.md',
    'MANIFESTO_TP4.md',
    'MATRIZ_RUBRICA_TP4.md',
    'ROTEIRO_VIDEO_TP4_5MIN.md',
    'TP4_FINAL_VALIDATION_SUMMARY.md',
    'README.md',
    'AUDITORIA_PRE_SUBMISSAO_TP4.md'
)
foreach ($name in $rootFiles) {
    Copy-Item -LiteralPath (Join-Path $repo $name) -Destination $packageRoot -Force
}

$manifestPath = Join-Path $packageRoot 'HASHES_SHA256.txt'
$hashLines = Get-ChildItem -LiteralPath $packageRoot -File -Recurse | Sort-Object FullName | ForEach-Object {
    $relative = $_.FullName.Substring($packageRoot.Length).TrimStart('\')
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash
    "$hash  $relative"
}
Set-Content -LiteralPath $manifestPath -Value $hashLines -Encoding utf8
Copy-Item -LiteralPath $manifestPath -Destination (Join-Path $repo 'HASHES_SHA256.txt') -Force

Compress-Archive -Path (Join-Path $packageRoot '*') -DestinationPath $zipPath -CompressionLevel Optimal

$zipHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $zipPath).Hash
$zipHashLine = "$zipHash  Igor_Monteiro_PB_TP4.ZIP"
$zipHashPath = Join-Path $deliveryRoot 'ZIP_SHA256.txt'
Set-Content -LiteralPath $zipHashPath -Value $zipHashLine -Encoding ascii
Set-Content -LiteralPath (Join-Path $repo 'ZIP_SHA256.txt') -Value $zipHashLine -Encoding ascii

Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead($zipPath)
try {
    $entries = @($archive.Entries)
    $names = @($entries | ForEach-Object FullName)
    $required = @(
        'verilog_tp4/rtl/safe_field_audio_energy_dsp.v',
        'verilog_tp4/rtl/safe_field_energy_bram.v',
        'assembly_tp4/safe_field_arm64.S',
        'docs_tp4/output/pdf/RELATORIO_TECNICO_SAFE_FIELD_TP4.pdf',
        'AUDITORIA_PRE_SUBMISSAO_TP4.md',
        'MATRIZ_RUBRICA_TP4.md',
        'LINKS_ENTREGA_TP4.md',
        'HASHES_SHA256.txt'
    )
    foreach ($requiredName in $required) {
        if ($names -notcontains $requiredName) {
            throw "ZIP missing required entry: $requiredName"
        }
    }
    if ($names -match '(^|/)(\.git|__pycache__|\.pytest_cache|\.cache)(/|$)') {
        throw 'ZIP contains a forbidden cache or Git path.'
    }
    if ($names -match '\.(mp4|mov|avi|mkv|webm)$') {
        throw 'ZIP contains a video file; only delivery links are allowed.'
    }
    $entryCount = $entries.Count
}
finally {
    $archive.Dispose()
}

Write-Output "ZIP_PATH=$zipPath"
Write-Output "ZIP_SHA256=$zipHash"
Write-Output "ZIP_ENTRIES=$entryCount"
Write-Output "MANIFEST_ENTRIES=$($hashLines.Count)"
