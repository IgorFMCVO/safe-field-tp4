$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$expectedFinalHash = '0B04C9DF3F51B408932ED75B754F7F180001F02C50594B14CC685B4CE1BFFE8B'
$expectedGaoHash = '64A06F844FF63560384455ADA08B7F0C768BBA6A818579F87BDC5F6993968E56'
$finalFs = Join-Path $projectRoot 'build\full\impl\pnr\safe_field_tp4.fs'
$gaoFs = Join-Path $projectRoot 'build\physical_gao\impl\pnr\safe_field_tp4_physical_gao.fs'
$report = Join-Path $projectRoot 'build\physical_gao\impl\pnr\safe_field_tp4_gao.rpt.txt'
$timing = Join-Path $projectRoot 'build\physical_gao\impl\pnr\safe_field_tp4_gao.tr'

if ((Get-FileHash -Algorithm SHA256 -LiteralPath $finalFs).Hash -ne $expectedFinalHash) {
    throw 'Production safe_field_tp4.fs hash changed'
}
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $gaoFs).Hash -ne $expectedGaoHash) {
    throw 'GAO bitstream hash mismatch'
}

$reportText = Get-Content -Raw -LiteralPath $report
foreach ($entry in ([ordered]@{
    sys_clk='45/1'; pi_signal='40/1'; i2s_sck='41/1'; i2s_ws='42/1'; i2s_sd='43/1'; led='10/0'
}).GetEnumerator()) {
    $pattern = '(?m)^' + [regex]::Escape($entry.Key) + '\s+\|.*\|\s*' + [regex]::Escape($entry.Value) + '\s+\|'
    if ($reportText -notmatch $pattern) { throw "GAO pin mismatch: $($entry.Key)" }
}

$timingText = Get-Content -Raw -LiteralPath $timing
if ($timingText -notmatch '<Numbers of Setup Violated Endpoints>:0' -or
    $timingText -notmatch '<Numbers of Hold Violated Endpoints>:0') {
    throw 'GAO timing violations present'
}

$captureNames = @('silence', 'tone_500hz', 'tone_1000hz', 'tone_2000hz', 'pulses_1000hz')
foreach ($name in $captureNames) {
    $jsonPath = Join-Path $projectRoot "evidence\physical\gao_${name}_analysis.json"
    $capture = Get-Content -Raw -LiteralPath $jsonPath | ConvertFrom-Json
    if ($capture.derived_clocks.sck_hz_from_measured_divider -ne 2700000) { throw "$name SCK mismatch" }
    if ($capture.derived_clocks.ws_hz_from_measured_half_divider -ne 42187.5) { throw "$name WS mismatch" }
    if ($capture.core0.sample_valid_high_samples -le 0) { throw "$name has no sample_valid" }
    if ($capture.core0.frame_error_high_samples -ne 0) { throw "$name has frame errors" }
    if ($capture.core0.sd_transitions -ne 0) { throw "$name unexpectedly has SD transitions" }
    if ($capture.core1.sample_nonzero_rows -ne 0) { throw "$name unexpectedly has nonzero samples" }
    if ($capture.core1.energy.max -ne 0) { throw "$name unexpectedly has nonzero energy" }
    "capture=$name clock_generation=PASS sample_valid=PASS frame_errors=0 sd_activity=FAIL samples_nonzero=FAIL"
}

"production_fs_sha256=$expectedFinalHash"
"gao_fs_sha256=$expectedGaoHash"
'PHYSICAL_EVIDENCE_AUDIT=PASS (evidence consistent; audio path fails at SD activity)'
