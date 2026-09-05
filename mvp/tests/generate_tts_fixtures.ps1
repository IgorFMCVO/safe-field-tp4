param(
    [string]$OutputRoot = "mvp/generated_audio"
)

$ErrorActionPreference = "Stop"

$absoluteRoot = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $OutputRoot))
[System.IO.Directory]::CreateDirectory($absoluteRoot) | Out-Null

$manifestPath = Join-Path (Split-Path -Parent $PSCommandPath) "scenario_ground_truth.json"
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$installed = @{}
$probe = New-Object -ComObject SAPI.SpVoice
foreach ($voice in $probe.GetVoices()) {
    $installed[$voice.GetDescription().Split(' - ')[0]] = $voice
}

foreach ($scenario in $manifest.scenarios) {
    $scenarioRoot = Join-Path $absoluteRoot $scenario.scenario_id
    [System.IO.Directory]::CreateDirectory($scenarioRoot) | Out-Null
    foreach ($segment in $scenario.segments) {
        if (-not $installed.ContainsKey($segment.voice)) {
            throw "Required offline SAPI voice not installed: $($segment.voice)"
        }
        $target = Join-Path $scenarioRoot ($segment.segment_id + ".wav")
        $speaker = New-Object -ComObject SAPI.SpVoice
        $stream = New-Object -ComObject SAPI.SpFileStream
        try {
            $speaker.Voice = $installed[$segment.voice]
            $speaker.Rate = [int]$segment.rate
            $speaker.Volume = 85
            # SAFT16kHz16BitMono = 18; SSFMCreateForWrite = 3.
            $stream.Format.Type = 18
            $stream.Open($target, 3, $false)
            $speaker.AudioOutputStream = $stream
            $utterance = [string]$segment.transcript
            $flags = 0
            if ($null -ne $segment.pitch -and [int]$segment.pitch -ne 0) {
                $escaped = [System.Security.SecurityElement]::Escape($utterance)
                $utterance = "<pitch middle='$([int]$segment.pitch)'>$escaped</pitch>"
                $flags = 8 # SVSFIsXML
            }
            [void]$speaker.Speak($utterance, $flags)
        }
        finally {
            $stream.Close()
            [System.Runtime.InteropServices.Marshal]::ReleaseComObject($stream) | Out-Null
            [System.Runtime.InteropServices.Marshal]::ReleaseComObject($speaker) | Out-Null
        }
    }
}

$files = Get-ChildItem -LiteralPath $absoluteRoot -Recurse -Filter *.wav
$hashes = foreach ($file in $files) {
    [ordered]@{
        path = $file.FullName.Substring($absoluteRoot.Length + 1).Replace('\', '/')
        bytes = $file.Length
        sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
    }
}
$evidence = [ordered]@{
    generated_at = [DateTimeOffset]::Now.ToString("o")
    generator = "Windows SAPI.SpVoice offline TTS"
    sample_rate = 16000
    bits = 16
    channels = 1
    files = $hashes
}
$evidence | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $absoluteRoot "TTS_MANIFEST.json") -Encoding utf8
Write-Host "PASS generated $($files.Count) offline TTS fixtures in $absoluteRoot"
