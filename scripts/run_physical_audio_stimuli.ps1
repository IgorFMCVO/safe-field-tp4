param(
    [double]$Amplitude = 0.12,
    [int]$CaptureTimeoutMs = 15000
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$evidenceRoot = Join-Path $projectRoot 'evidence\physical'
$stimulusRoot = Join-Path $evidenceRoot 'stimuli'
$gao = 'C:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gao_sh.exe'
$rao = Join-Path $projectRoot 'src\safe_field_tp4_gao.rao'
$log = Join-Path $evidenceRoot 'gao_audio_stimuli.log'
New-Item -ItemType Directory -Force -Path $stimulusRoot | Out-Null

function New-TestWave {
    param([string]$Path, [double]$Frequency, [switch]$Pulsed)
    $sampleRate = 48000
    $durationSeconds = 3
    $sampleCount = $sampleRate * $durationSeconds
    $writer = [System.IO.BinaryWriter]::new([System.IO.File]::Open($Path, [System.IO.FileMode]::Create))
    try {
        $dataBytes = $sampleCount * 2
        $writer.Write([Text.Encoding]::ASCII.GetBytes('RIFF'))
        $writer.Write([int](36 + $dataBytes))
        $writer.Write([Text.Encoding]::ASCII.GetBytes('WAVEfmt '))
        $writer.Write([int]16)
        $writer.Write([int16]1)
        $writer.Write([int16]1)
        $writer.Write([int]$sampleRate)
        $writer.Write([int]($sampleRate * 2))
        $writer.Write([int16]2)
        $writer.Write([int16]16)
        $writer.Write([Text.Encoding]::ASCII.GetBytes('data'))
        $writer.Write([int]$dataBytes)
        for ($index = 0; $index -lt $sampleCount; $index++) {
            $enabled = (-not $Pulsed) -or (($index % 28800) -lt 14400)
            $value = if ($enabled) {
                [int16]([Math]::Round(32767 * $Amplitude * [Math]::Sin(2 * [Math]::PI * $Frequency * $index / $sampleRate)))
            } else { [int16]0 }
            $writer.Write($value)
        }
    } finally {
        $writer.Dispose()
    }
}

$stimuli = @(
    [pscustomobject]@{Name='silence'; Frequency=0; Pulsed=$false},
    [pscustomobject]@{Name='tone_500hz'; Frequency=500; Pulsed=$false},
    [pscustomobject]@{Name='tone_1000hz'; Frequency=1000; Pulsed=$false},
    [pscustomobject]@{Name='tone_2000hz'; Frequency=2000; Pulsed=$false},
    [pscustomobject]@{Name='pulses_1000hz'; Frequency=1000; Pulsed=$true}
)

$logLines = [System.Collections.Generic.List[string]]::new()
$logLines.Add('started_local=' + (Get-Date -Format o))
$logLines.Add('amplitude_fraction_full_scale=' + $Amplitude)
$logLines.Add('capture=GAO/JTAG physical hardware')

foreach ($stimulus in $stimuli) {
    $player = $null
    if ($stimulus.Frequency -gt 0) {
        $wav = Join-Path $stimulusRoot ($stimulus.Name + '.wav')
        New-TestWave -Path $wav -Frequency $stimulus.Frequency -Pulsed:$stimulus.Pulsed
        $player = [System.Media.SoundPlayer]::new($wav)
        $player.Load()
        $player.PlayLooping()
        Start-Sleep -Milliseconds 300
    } else {
        Start-Sleep -Milliseconds 500
    }

    $prefix = Join-Path $evidenceRoot ('gao_' + $stimulus.Name)
    $logLines.Add(('stimulus_start name={0} local={1}' -f $stimulus.Name, (Get-Date -Format o)))
    $process = Start-Process -FilePath $gao -ArgumentList @(
        '-gao', $rao, '-out', $prefix, '-device', 'GW1NSR-4C',
        '-cable', 'FT2CH', '-location', '0'
    ) -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit($CaptureTimeoutMs)) {
        $process.Kill()
        if ($player) { $player.Stop() }
        throw "GAO capture timed out for $($stimulus.Name)"
    }
    if ($player) { $player.Stop() }

    $core0 = $prefix + '_core0_window0.csv'
    $core1 = $prefix + '_core1_window0.csv'
    if (-not (Test-Path -LiteralPath $core0) -or -not (Test-Path -LiteralPath $core1)) {
        throw "GAO did not export both cores for $($stimulus.Name)"
    }
    $logLines.Add(('stimulus_finish name={0} local={1} core0={2} core1={3}' -f
        $stimulus.Name, (Get-Date -Format o), $core0, $core1))
    Start-Sleep -Milliseconds 500
}

$logLines.Add('finished_local=' + (Get-Date -Format o))
$logLines | Set-Content -LiteralPath $log -Encoding utf8
$logLines
