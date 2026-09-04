$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot

$hashes = [ordered]@{
    'build\full\impl\pnr\safe_field_tp4.fs' = '0B04C9DF3F51B408932ED75B754F7F180001F02C50594B14CC685B4CE1BFFE8B'
    'build\debug1_i2s_internal_activity\impl\pnr\debug1_i2s_internal_activity.fs' = 'F1011244D4CB641A7526E031E2AC1EB74D4FE4DC12D23CF59E525B5F28BC3EBF'
    'build\debug2_sd_transition_detect\impl\pnr\debug2_sd_transition_detect.fs' = '372114B1DED654BDE00DE151D9F38EA06A8E66E8FB60C9524E1F16C772DEB475'
    'build\debug3_nonzero_sample\impl\pnr\debug3_nonzero_sample.fs' = 'D06F286F0551E4E0AEECF88E2E97021B1B4C2E08C7D90E5B871C962F3E4694A4'
    'build\debug4_low_threshold_audio\impl\pnr\debug4_low_threshold_audio.fs' = 'AD16B4EDDCD476633E0FDF755482B63B5AF6174A98C69F762DD75BB30D301487'
    'build\debug5_external_wiring_levels\impl\pnr\debug5_external_wiring_levels.fs' = '712A05C5102B2D61895761769C386D6521D34BBFBB386F7B33A6B9294380C3D6'
    'build\debug6_low_rate_i2s\impl\pnr\ao_0.fs' = 'D930622FF7C1407D33C0EA0B2324B7DFB8892E6FDE08B98F2A4D40F603876105'
    'build\debug7_sd_slot_diagnostic_none\impl\pnr\ao_0.fs' = '3A6FD06F8B4515DEFF827F42EBC83D1FC56033DE817D147F567D3919C278AE7E'
    'build\debug7_sd_slot_diagnostic_up\impl\pnr\ao_0.fs' = '4C5ED5A0DE02ABCA1C6E2AF26039A469EF4F7E32958A018E434A798A04EE3DAC'
}

foreach ($entry in $hashes.GetEnumerator()) {
    $path = Join-Path $projectRoot $entry.Key
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash
    if ($actual -ne $entry.Value) { throw "SHA-256 mismatch: $($entry.Key)" }
    "HASH PASS $($entry.Key) $actual"
}

$builds = @(
    [pscustomobject]@{Name='debug6_low_rate_i2s'; Pull='DOWN'},
    [pscustomobject]@{Name='debug7_sd_slot_diagnostic_none'; Pull='NONE'},
    [pscustomobject]@{Name='debug7_sd_slot_diagnostic_up'; Pull='UP'}
)
foreach ($build in $builds) {
    $pnr = Join-Path $projectRoot "build\$($build.Name)\impl\pnr"
    $report = Get-Content -Raw -LiteralPath (Join-Path $pnr "$($build.Name).rpt.txt")
    $timing = Get-Content -Raw -LiteralPath (Join-Path $pnr "$($build.Name).tr")
    foreach ($signal in ([ordered]@{
        sys_clk='45/1'; pi_signal='40/1'; i2s_sck='41/1'; i2s_ws='42/1';
        i2s_sd='43/1'; led='10/0'
    }).GetEnumerator()) {
        $pattern = '(?m)^' + [regex]::Escape($signal.Key) + '\s+\|.*\|\s*' +
                   [regex]::Escape($signal.Value) + '\s+\|'
        if ($report -notmatch $pattern) { throw "$($build.Name) pin mismatch $($signal.Key)" }
    }
    $sdPattern = '(?m)^i2s_sd\s+\|.*\|\s*43/1\s+\|.*\|\s*in\s+\|.*\|\s*LVCMOS33\s+\|.*\|\s*' + $build.Pull + '\s+\|'
    if ($report -notmatch $sdPattern) { throw "$($build.Name) SD pull/direction mismatch" }
    if ($timing -notmatch '<Numbers of Setup Violated Endpoints>:0' -or
        $timing -notmatch '<Numbers of Hold Violated Endpoints>:0') {
        throw "$($build.Name) has timing violations"
    }
    "BUILD PASS $($build.Name) pinout=PRESERVED sd_pull=$($build.Pull) STA=PASS"
}

$gateA = Get-Content -Raw -LiteralPath (Join-Path $projectRoot 'evidence\physical\debug6_low_rate_i2s\gate_a_initial_analysis.json') | ConvertFrom-Json
if ($gateA.derived_clocks.sck_hz_from_measured_divider -ne 500000) { throw 'GATE A SCK mismatch' }
if ($gateA.core0.sd_transitions -ne 0) { throw 'GATE A unexpectedly has SD transitions' }
if ($gateA.core1.sample.count -ne 512 -or $gateA.core1.sample_nonzero_rows -ne 0) { throw 'GATE A sample evidence mismatch' }
if ($gateA.core0.frame_error_high_samples -ne 0) { throw 'GATE A frame errors present' }
'GATE_A=FAIL_EXPECTED clocks=PASS sd_transitions=0 left_nonzero=0/512 frame_errors=0'

foreach ($capture in @('pull_none','pull_up','pull_up_tone_1000hz')) {
    $json = Get-Content -Raw -LiteralPath (Join-Path $projectRoot "evidence\physical\debug7_sd_slot_diagnostic\${capture}_slot_analysis.json") | ConvertFrom-Json
    if ($json.clocks.sck_hz -ne 500000 -or $json.clocks.ws_hz -ne 7812.5 -or
        $json.clocks.sck_periods_per_frame -ne 64) { throw "$capture clock mismatch" }
    if (-not $json.raw_sd.all_high -or $json.raw_sd.transitions -ne 0) { throw "$capture SD not constant HIGH" }
    if ($json.samples.count -ne 512 -or $json.samples.min -ne -1 -or $json.samples.max -ne -1) { throw "$capture sample bias mismatch" }
    if ($json.frame_errors.counter_last -ne 0) { throw "$capture frame errors present" }
    "GATE_B_CAPTURE PASS_DIAGNOSTIC $capture SCK=500000 WS=7812.5 frame_sck=64 SD=HIGH_CONSTANT samples=-1x512 errors=0"
}

'AUDIO_ACCEPTANCE=FAIL'
'PRINCIPAL_SUSPECT=INMP441_MODULE_OR_SD_OUTPUT_STAGE'
'RESIDUAL_ALTERNATIVE=OPEN_CIRCUIT_BETWEEN_INMP441_SD_PAD_AND_FPGA_PIN43'
'PHYSICAL_EVIDENCE_STRENGTH=STRONG'
