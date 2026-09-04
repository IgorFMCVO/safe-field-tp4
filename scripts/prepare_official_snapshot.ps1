$ErrorActionPreference = 'Stop'

$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if ($repo -ne 'C:\SAFE-FIELD\fpga\tp4-audio-inmp441') {
    throw "Unexpected repository path: $repo"
}

$verilog = Join-Path $repo 'verilog_tp4'
$docs = Join-Path $repo 'docs_tp4'
$selectedAudio = Join-Path $docs 'evidence_physical\audio'
$selectedBridge = Join-Path $docs 'evidence_physical\mvp_hw_bridge'
$docsWaveforms = Join-Path $docs 'waveforms'
$bitstreams = Join-Path $verilog 'bitstreams'
$verilogBuild = Join-Path $verilog 'build'
$verilogEvidence = Join-Path $verilog 'evidence'

New-Item -ItemType Directory -Force -Path $selectedAudio, $selectedBridge, $docsWaveforms, $bitstreams, $verilogBuild, $verilogEvidence | Out-Null

# Build e evidências acadêmicas independentes.
Copy-Item -LiteralPath (Join-Path $repo 'build\safe_field_tp4_official') `
    -Destination $verilogBuild -Recurse -Force
Copy-Item -LiteralPath (Join-Path $repo 'build\safe_field_tp4_official_bidirectional') `
    -Destination $verilogBuild -Recurse -Force
Copy-Item -LiteralPath (Join-Path $repo 'evidence\official_tp4') `
    -Destination $verilogEvidence -Recurse -Force

# Scripts reproduzíveis ficam junto ao snapshot Verilog.
$scriptCopies = @(
    'sim\run-official-rubric.mjs',
    'scripts\analyze_physical_dsp_energy.py',
    'scripts\render_official_vcd.py'
)
foreach ($relative in $scriptCopies) {
    Copy-Item -LiteralPath (Join-Path $repo $relative) `
        -Destination (Join-Path $verilog 'scripts') -Force
}

# Três bitstreams com nomes inequívocos; nenhum arquivo original é modificado.
Copy-Item -LiteralPath (Join-Path $repo 'build\safe_field_tp4_audio_stable_iter2\impl\pnr\safe_field_tp4_validated.fs') `
    -Destination (Join-Path $bitstreams 'safe_field_tp4_validated.fs') -Force
Copy-Item -LiteralPath (Join-Path $repo 'build\safe_field_tp4_official\impl\pnr\safe_field_tp4_official.fs') `
    -Destination (Join-Path $bitstreams 'safe_field_tp4_official.fs') -Force
Copy-Item -LiteralPath (Join-Path $repo 'build\safe_field_tp4_official_bidirectional\impl\pnr\safe_field_tp4_official_bidirectional.fs') `
    -Destination (Join-Path $bitstreams 'safe_field_tp4_official_bidirectional.fs') -Force

# Evidências físicas mínimas e suficientes para auditoria acadêmica.
$physicalBase = Join-Path $repo 'evidence\physical\retest_after_contact_fix'
$audioFiles = @(
    'GATE_A_RESULT.md',
    'RETEST_STATUS.md',
    'OPERATOR_CONFIRMATION_10CYCLES.md',
    'STABLE_CUED_DIAGNOSTIC_SUMMARY.md',
    'normal_silence_reference_01_analysis.json',
    'normal_silence_reference_01_continuous_samples.csv',
    'normal_silence_reference_01_gao.log',
    'normal_silence_reference_01_waveform_distribution.png',
    'normal_voice_real_01_analysis.json',
    'normal_voice_real_01_continuous_samples.csv',
    'normal_voice_real_01_gao.log',
    'normal_voice_real_01_waveform_distribution.png',
    'normal_claps_real_01_analysis.json',
    'normal_claps_real_01_clap_analysis.json',
    'normal_claps_real_01_continuous_samples.csv',
    'normal_claps_real_01_gao.log',
    'normal_claps_real_01_clap_amplitude_time.png',
    'normal_claps_real_01_waveform_distribution.png',
    'normal_voice_vs_silence_comparison.json',
    'stable_cued_fsm_10cycles_04_valid_energy_analysis.json',
    'stable_cued_fsm_10cycles_04_valid_energy_timeline.png',
    'stable_cued_fsm_10cycles_04_valid_gao.log'
)
foreach ($name in $audioFiles) {
    Copy-Item -LiteralPath (Join-Path $physicalBase $name) -Destination $selectedAudio -Force
}

Copy-Item -LiteralPath (Join-Path $repo 'evidence\physical\PHYSICAL_DIAGNOSTIC_LOG.md') `
    -Destination (Join-Path $docs 'evidence_physical') -Force
Copy-Item -Path (Join-Path $repo 'evidence\mvp_hw_bridge\*') `
    -Destination $selectedBridge -Recurse -Force
Copy-Item -LiteralPath (Join-Path $repo 'MANIFESTO_TP4.md') `
    -Destination (Join-Path $docs 'MANIFESTO_TP4.md') -Force
Copy-Item -LiteralPath (Join-Path $repo 'TP4_FINAL_VALIDATION_SUMMARY.md') `
    -Destination (Join-Path $docs 'TP4_FINAL_VALIDATION_SUMMARY.md') -Force
Copy-Item -LiteralPath (Join-Path $repo 'MVP_HW_BRIDGE_STATUS.md') `
    -Destination (Join-Path $docs 'MVP_HW_BRIDGE_STATUS.md') -Force

$waveformPngs = @(
    'dsp_expected_actual_waveform.png',
    'uart_command_crc_waveform.png'
)
foreach ($name in $waveformPngs) {
    Copy-Item -LiteralPath (Join-Path $repo "evidence\official_tp4\waveforms\$name") `
        -Destination $docsWaveforms -Force
}

Write-Output 'OFFICIAL_SNAPSHOT_PREPARED'
