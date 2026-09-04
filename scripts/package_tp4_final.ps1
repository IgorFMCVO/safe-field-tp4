[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$workspaceRoot = [System.IO.Path]::GetFullPath((Join-Path $repoRoot '..\..'))
$deliveryRoot = [System.IO.Path]::GetFullPath((Join-Path $workspaceRoot 'DELIVERY_TP4_FINAL'))
$expectedRoot = [System.IO.Path]::GetFullPath('C:\SAFE-FIELD\DELIVERY_TP4_FINAL')

if ($deliveryRoot -ne $expectedRoot) {
    throw "Unsafe delivery target: $deliveryRoot"
}

if (Test-Path -LiteralPath $deliveryRoot) {
    $resolvedExisting = (Resolve-Path -LiteralPath $deliveryRoot).Path
    if ($resolvedExisting -ne $expectedRoot) {
        throw "Refusing to replace unexpected directory: $resolvedExisting"
    }
    Remove-Item -LiteralPath $resolvedExisting -Recurse -Force
}

$packageName = 'SAFE_FIELD_TP4_Igor_de_Freitas_Monteiro'
$contentRoot = Join-Path $deliveryRoot $packageName
New-Item -ItemType Directory -Path $contentRoot -Force | Out-Null

function Copy-Artifact {
    param(
        [Parameter(Mandatory = $true)][string]$SourceRelative,
        [Parameter(Mandatory = $true)][string]$DestinationRelative
    )

    $source = Join-Path $repoRoot $SourceRelative
    if (-not (Test-Path -LiteralPath $source)) {
        throw "Required artifact missing: $source"
    }
    $destination = Join-Path $contentRoot $DestinationRelative
    $parent = Split-Path -Parent $destination
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination -Recurse -Force
}

# Entry documents.
Copy-Artifact 'delivery_tp4\README_PRIMEIRO_TP4.md' 'README_PRIMEIRO_TP4.md'
Copy-Artifact 'delivery_tp4\MANIFESTO_ENTREGA_TP4.md' 'MANIFESTO_ENTREGA_TP4.md'
Copy-Artifact 'delivery_tp4\CHECKLIST_ENTREGA_TP4.md' 'CHECKLIST_ENTREGA_TP4.md'
Copy-Artifact 'delivery_tp4\COMANDOS_REPRODUCAO_TP4.md' 'docs\COMANDOS_REPRODUCAO_TP4.md'

# Final reports and architecture.
foreach ($doc in @(
    'TP4_FINAL_VALIDATION_SUMMARY.md',
    'AUDIO_ACCEPTANCE_REPORT.md',
    'STATUS_TP4.md',
    'README_TP4_DELIVERY.md',
    'PINOUT_REQUIRED.md',
    'MVP_ARCHITECTURE.md'
)) {
    Copy-Artifact $doc (Join-Path 'docs' $doc)
}

# Frozen TP4 RTL and constraints.
foreach ($file in @(
    'rasp_to_tang.v',
    'i2s_clock_gen.v',
    'i2s_rx_24.v',
    'audio_energy_detector_persistent.v',
    'audio_activity_fsm_persistent.v',
    'safe_field_tp4_audio_stable.v',
    'safe_field_tp4_audio_stable.rao',
    'safe_field_tp4.cst',
    'safe_field_tp4.sdc'
)) {
    Copy-Artifact (Join-Path 'src' $file) (Join-Path 'rtl' $file)
}

foreach ($file in @(
    'tb_audio_activity_fsm_persistent.v',
    'tb_fsm_physical_regression.v',
    'tb_fsm_final_cued_regression.v',
    'tb_safe_field_tp4_audio_stable.v',
    'tb_end_to_end.v'
)) {
    Copy-Artifact (Join-Path 'tb' $file) (Join-Path 'testbenches' $file)
}

Copy-Artifact 'scripts' 'scripts'
Copy-Artifact 'sim' 'simulation'

# Frozen bitstream and complete final implementation reports.
Copy-Artifact 'build\safe_field_tp4_audio_stable_iter2\impl\pnr\safe_field_tp4_validated.fs' 'bitstream\safe_field_tp4_validated.fs'
Copy-Artifact 'build\safe_field_tp4_audio_stable_iter2\impl' 'gowin_reports\safe_field_tp4_audio_stable_iter2_impl'

# All preserved evidence, including failed/intermediate evidence for auditability.
Copy-Artifact 'evidence' 'evidence'
Copy-Artifact '20260831_151428.mp4' 'media\20260831_151428_gpio17_baseline.mp4'

# FPGA-to-Raspberry MVP is explicitly supplemental, not the TP4 bitstream.
foreach ($file in @(
    'MVP_HW_BRIDGE_STATUS.md',
    'MVP_NEXT_STEPS.md',
    'UART_PROTOCOL_V1.md'
)) {
    Copy-Artifact $file (Join-Path 'supplemental_mvp' $file)
}
Copy-Artifact 'raspberry' 'supplemental_mvp\raspberry'
foreach ($file in @(
    'safe_field_mvp_hw_bridge.v',
    'safe_field_mvp_hw_bridge.cst',
    'safe_field_telemetry_tx.v',
    'uart_tx_byte.v'
)) {
    Copy-Artifact (Join-Path 'src' $file) (Join-Path 'supplemental_mvp\fpga' $file)
}
foreach ($file in @(
    'tb_safe_field_mvp_hw_bridge.v',
    'tb_safe_field_telemetry_tx.v',
    'tb_uart_tx_byte.v'
)) {
    Copy-Artifact (Join-Path 'tb' $file) (Join-Path 'supplemental_mvp\testbenches' $file)
}
Copy-Artifact 'build\safe_field_mvp_hw_bridge\impl\pnr\safe_field_mvp_hw_bridge.fs' 'supplemental_mvp\bitstream\safe_field_mvp_hw_bridge.fs'

# Remove generated caches if any were copied by local test execution.
Get-ChildItem -LiteralPath $contentRoot -Directory -Recurse -Force |
    Where-Object { $_.Name -in @('__pycache__', 'node_modules', '.pytest_cache') } |
    Sort-Object FullName -Descending |
    ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }
Get-ChildItem -LiteralPath $contentRoot -File -Recurse -Force |
    Where-Object { $_.Extension -in @('.pyc', '.pyo') -or $_.Name -like '*.tmp' } |
    ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force }

# Verify official bitstream before producing the manifest.
$officialFs = Join-Path $contentRoot 'bitstream\safe_field_tp4_validated.fs'
$officialHash = (Get-FileHash -LiteralPath $officialFs -Algorithm SHA256).Hash
$expectedOfficialHash = '5D8F2D31EF5D0349AC0E52F13AC8A7472FCB1A23103131D13163BB8946F39181'
if ($officialHash -ne $expectedOfficialHash) {
    throw "Official bitstream hash mismatch: $officialHash"
}

$hashFile = Join-Path $contentRoot 'HASHES_SHA256.txt'
$hashLines = Get-ChildItem -LiteralPath $contentRoot -File -Recurse |
    Where-Object { $_.FullName -ne $hashFile } |
    Sort-Object FullName |
    ForEach-Object {
        $relative = $_.FullName.Substring($contentRoot.Length + 1).Replace('\', '/')
        $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
        "$hash  $relative"
    }
Set-Content -LiteralPath $hashFile -Value $hashLines -Encoding utf8

$zipPath = Join-Path $deliveryRoot "$packageName.zip"
Compress-Archive -LiteralPath $contentRoot -DestinationPath $zipPath -CompressionLevel Optimal -Force
$zipHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash
Set-Content -LiteralPath (Join-Path $deliveryRoot 'ZIP_SHA256.txt') -Value "$zipHash  $packageName.zip" -Encoding utf8

[pscustomobject]@{
    PackageDirectory = $contentRoot
    Zip = $zipPath
    ZipSHA256 = $zipHash
    Files = (Get-ChildItem -LiteralPath $contentRoot -File -Recurse).Count
    Bytes = (Get-ChildItem -LiteralPath $contentRoot -File -Recurse | Measure-Object Length -Sum).Sum
    OfficialBitstreamSHA256 = $officialHash
}
