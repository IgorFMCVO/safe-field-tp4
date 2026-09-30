param(
    [string]$ModelsRoot = "C:\SAFE-FIELD\fpga\tp4-audio-inmp441\mvp\evidence\models",
    [string]$SpoolRoot = "$env:LOCALAPPDATA\Temp\safe-field-operational-20260921\worker-spool",
    [string]$LogRoot = "$env:LOCALAPPDATA\Temp\safe-field-operational-20260921",
    [string]$TokenFile = "$env:LOCALAPPDATA\safe-field-runtime\razer-worker.token",
    [ValidateSet('community1', 'recovery')]
    [string]$DiarizationEngine = $(if ($env:DIARIZATION_ENGINE) { $env:DIARIZATION_ENGINE } else { 'community1' }),
    [string]$Community1Python = "C:\SAFE-FIELD\_checkpoints\gate2c_ab_20260930T002124Z_3a68721c\community1_venv\Scripts\python.exe",
    [string]$Community1CacheRoot = "C:\SAFE-FIELD\_checkpoints\gate2c_ab_20260930T002124Z_3a68721c\community1_cache",
    [string]$Community1ModelSnapshot = "C:\SAFE-FIELD\_checkpoints\gate2c_ab_20260930T002124Z_3a68721c\community1_cache\models--pyannote--speaker-diarization-community-1\snapshots\3533c8cf8e369892e6b79ff1bf80f7b0286a54ee"
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $TokenFile)) {
    throw "Razer worker token file not found: $TokenFile"
}
$env:SAFE_FIELD_RAZER_WORKER_TOKEN = (Get-Content -LiteralPath $TokenFile -Raw).Trim()
if ([string]::IsNullOrWhiteSpace($env:SAFE_FIELD_RAZER_WORKER_TOKEN)) {
    throw 'Razer worker token file is empty.'
}

$pythonw = 'C:\SAFE-FIELD\fpga\tp4-audio-inmp441\mvp\evidence\recovery_venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonw)) { throw "pythonw.exe not found: $pythonw" }
if ($DiarizationEngine -eq 'community1') {
    if (-not (Test-Path -LiteralPath $Community1Python)) { throw "Community-1 Python not found: $Community1Python" }
    if (-not (Test-Path -LiteralPath $Community1CacheRoot)) { throw "Community-1 cache not found: $Community1CacheRoot" }
    if (-not (Test-Path -LiteralPath $Community1ModelSnapshot)) { throw "Community-1 snapshot not found: $Community1ModelSnapshot" }
}
New-Item -ItemType Directory -Force -Path $LogRoot, $SpoolRoot | Out-Null

# pythonw detaches the worker from a transient terminal; faulthandler keeps any
# native failure in the persistent stderr log instead of a closing console.
$env:PYTHONFAULTHANDLER = '1'
$env:PYTHONUNBUFFERED = '1'
$env:DIARIZATION_ENGINE = $DiarizationEngine
$out = Join-Path $LogRoot 'razer-worker.stdout.log'
$err = Join-Path $LogRoot 'razer-worker.stderr.log'
$args = @('-m', 'mvp.razer_worker_service', '--bind', '127.0.0.1', '--port', '8766',
          '--models-root', $ModelsRoot, '--provider-timeout', '90', '--spool-root', $SpoolRoot,
          '--diarization-engine', $DiarizationEngine,
          '--community1-python', $Community1Python,
          '--community1-cache-root', $Community1CacheRoot,
          '--community1-model-snapshot', $Community1ModelSnapshot)
$process = Start-Process -FilePath $pythonw -ArgumentList $args -WindowStyle Hidden `
    -RedirectStandardOutput $out -RedirectStandardError $err -PassThru
Write-Output "RAZER_WORKER_PID=$($process.Id)"
