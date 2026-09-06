param([string]$Manifest, [string]$OutputRoot = 'mvp/generated_audio/real_occurrence_01', [switch]$Probe)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path (Get-Location) $OutputRoot))
[IO.Directory]::CreateDirectory($root) | Out-Null
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.SpeechSynthesis.SpeechSynthesizer, Windows.Media.SpeechSynthesis, ContentType=WindowsRuntime]
$null = [Windows.Media.SpeechSynthesis.SpeechSynthesisStream, Windows.Media.SpeechSynthesis, ContentType=WindowsRuntime]
$voices = [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | Select-Object -First 1
$audit = @()
$utterances = if ($Probe) { @($voices | ForEach-Object { [pscustomobject]@{id=$_.DisplayName.Replace(' ','_');voice=$_.DisplayName;text='Meu nome é exemplo fictício. Sou policial e estou ouvindo seu relato.'} }) } else { (Get-Content -Raw -Encoding utf8 $Manifest | ConvertFrom-Json).utterances }
foreach ($u in $utterances) {
    $speaker = New-Object Windows.Media.SpeechSynthesis.SpeechSynthesizer
    $stream = $null
    try {
        $voice = $voices | Where-Object DisplayName -eq $u.voice | Select-Object -First 1
        if (-not $voice) { throw "Voice unavailable: $($u.voice)" }
        $speaker.Voice = $voice
        $path = Join-Path $root ($u.id + '.wav')
        $operation = $speaker.SynthesizeTextToStreamAsync([string]$u.text)
        $task = $asTask.MakeGenericMethod([Windows.Media.SpeechSynthesis.SpeechSynthesisStream]).Invoke($null, @($operation))
        $task.Wait()
        $stream = $task.Result
        $reader = [System.IO.WindowsRuntimeStreamExtensions]::AsStreamForRead($stream)
        $file = [IO.File]::Create($path)
        try { $reader.CopyTo($file) } finally { $file.Dispose(); $reader.Dispose() }
        $audit += [pscustomobject]@{id=$u.id; voice=$u.voice; language=$voice.Language; provider='Windows OneCore WinRT offline'; pitch_modified=$false; result='PASS'}
    } catch {
        $audit += [pscustomobject]@{id=$u.id;voice=$u.voice;result='FAIL';error=$_.Exception.Message}
        if (-not $Probe) { throw }
    } finally {
        $speaker.Dispose()
    }
}
$audit | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $root 'voice_manifest.json') -Encoding utf8
$audit | Format-Table id,voice,result
