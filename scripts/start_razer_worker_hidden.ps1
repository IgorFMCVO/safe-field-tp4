param(
    [string]$ModelsRoot = "C:\SAFE-FIELD\fpga\tp4-audio-inmp441\mvp\evidence\models",
    [string]$SpoolRoot = "$env:LOCALAPPDATA\Temp\safe-field-operational-20260921\worker-spool",
    [string]$LogRoot = "$env:LOCALAPPDATA\Temp\safe-field-operational-20260921",
    [string]$TokenFile = "$env:LOCALAPPDATA\safe-field-runtime\razer-worker.token"
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
New-Item -ItemType Directory -Force -Path $LogRoot, $SpoolRoot | Out-Null

# pythonw detaches the worker from a transient terminal; faulthandler keeps any
# native failure in the persistent stderr log instead of a closing console.
$env:PYTHONFAULTHANDLER = '1'
$env:PYTHONUNBUFFERED = '1'
$out = Join-Path $LogRoot 'razer-worker.stdout.log'
$err = Join-Path $LogRoot 'razer-worker.stderr.log'
$args = @('-m', 'mvp.razer_worker_service', '--bind', '127.0.0.1', '--port', '8766',
          '--models-root', $ModelsRoot, '--provider-timeout', '90', '--spool-root', $SpoolRoot)
$process = Start-Process -FilePath $pythonw -ArgumentList $args -WindowStyle Hidden `
    -RedirectStandardOutput $out -RedirectStandardError $err -PassThru
Write-Output "RAZER_WORKER_PID=$($process.Id)"
