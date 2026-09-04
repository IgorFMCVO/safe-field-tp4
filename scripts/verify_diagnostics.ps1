$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$originalFs = Join-Path $projectRoot 'build\full\impl\pnr\safe_field_tp4.fs'
$originalExpectedHash = '0B04C9DF3F51B408932ED75B754F7F180001F02C50594B14CC685B4CE1BFFE8B'
$originalActualHash = (Get-FileHash -LiteralPath $originalFs -Algorithm SHA256).Hash
if ($originalActualHash -ne $originalExpectedHash) {
    throw "Original safe_field_tp4.fs changed: $originalActualHash"
}

$expectedPins = [ordered]@{
    sys_clk   = '45/1'
    pi_signal = '40/1'
    i2s_sck   = '41/1'
    i2s_ws    = '42/1'
    i2s_sd    = '43/1'
    led       = '10/0'
}

$variants = @(
    'debug1_i2s_internal_activity',
    'debug2_sd_transition_detect',
    'debug3_nonzero_sample',
    'debug4_low_threshold_audio'
)

"original_fs_sha256=$originalActualHash"
foreach ($name in $variants) {
    $buildRoot = Join-Path $projectRoot "build\$name\impl"
    $synthesisLog = Join-Path $buildRoot "gwsynthesis\$name.log"
    $pnrRoot = Join-Path $buildRoot 'pnr'
    $pnrLog = Join-Path $pnrRoot "$name.log"
    $reportPath = Join-Path $pnrRoot "$name.rpt.txt"
    $timingPath = Join-Path $pnrRoot "$name.tr"
    $fsPath = Join-Path $pnrRoot "$name.fs"

    foreach ($requiredPath in @($synthesisLog, $pnrLog, $reportPath, $timingPath, $fsPath)) {
        if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
            throw "Missing artifact: $requiredPath"
        }
    }

    $synthesisText = Get-Content -Raw -LiteralPath $synthesisLog
    $pnrText = Get-Content -Raw -LiteralPath $pnrLog
    $reportText = Get-Content -Raw -LiteralPath $reportPath
    $timingText = Get-Content -Raw -LiteralPath $timingPath

    if ($synthesisText -match '(?m)^ERROR' -or $pnrText -match '(?m)^ERROR') {
        throw "$name contains an ERROR"
    }
    if ($pnrText -notmatch 'Placement and routing completed' -or
        $pnrText -notmatch 'Bitstream generation completed') {
        throw "$name did not complete P&R/bitstream generation"
    }
    if ($timingText -notmatch '<Numbers of Setup Violated Endpoints>:0' -or
        $timingText -notmatch '<Numbers of Hold Violated Endpoints>:0') {
        throw "$name has a timing violation"
    }
    foreach ($entry in $expectedPins.GetEnumerator()) {
        $pattern = '(?m)^' + [regex]::Escape($entry.Key) + '\s+\|.*\|\s*' +
                   [regex]::Escape($entry.Value) + '\s+\|'
        if ($reportText -notmatch $pattern) {
            throw "$name missing $($entry.Key) at $($entry.Value)"
        }
    }

    $warningCount = ([regex]::Matches($synthesisText + $pnrText, '(?m)^WARN')).Count
    $hash = (Get-FileHash -LiteralPath $fsPath -Algorithm SHA256).Hash
    $setupViolations = ([regex]::Match(
        $timingText, '<Numbers of Setup Violated Endpoints>:(\d+)')).Groups[1].Value
    $holdViolations = ([regex]::Match(
        $timingText, '<Numbers of Hold Violated Endpoints>:(\d+)')).Groups[1].Value
    "$name PNR=PASS STA=PASS setup_violations=$setupViolations hold_violations=$holdViolations warnings=$warningCount sha256=$hash"
}

'DIAGNOSTIC_AUDIT=PASS'
