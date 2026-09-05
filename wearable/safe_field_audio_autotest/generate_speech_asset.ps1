param(
    [string]$OutputWav = (Join-Path $PSScriptRoot "assets\safe_field_speech_mono_16k.wav")
)

$ErrorActionPreference = "Stop"
$assetDir = Split-Path -Parent $OutputWav
New-Item -ItemType Directory -Force -Path $assetDir | Out-Null

Add-Type -AssemblyName System.Speech
$voice = New-Object System.Speech.Synthesis.SpeechSynthesizer
$pt = $voice.GetInstalledVoices() | Where-Object {
    $_.Enabled -and $_.VoiceInfo.Culture.Name -eq "pt-BR"
} | Select-Object -First 1
if (-not $pt) { throw "No enabled pt-BR SAPI voice is installed" }

$voice.SelectVoice($pt.VoiceInfo.Name)
$voice.Rate = 6
$voice.Volume = 100
$format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(
    16000,
    [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
    [System.Speech.AudioFormat.AudioChannel]::Mono
)
$voice.SetOutputToWaveFile($OutputWav, $format)
$voice.Speak("SAFE FIELD. TESTE DE VOZ UM DOIS TRÊS. SISTEMA DE CAPTAÇÃO ATIVO.")
$voice.SetOutputToNull()
$voice.Dispose()

Write-Output "VOICE=$($pt.VoiceInfo.Name)"
Write-Output "WAV=$OutputWav"
