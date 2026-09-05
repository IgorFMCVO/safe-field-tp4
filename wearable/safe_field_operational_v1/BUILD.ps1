param(
    [string]$Port = "COM7",
    [switch]$Upload,
    [switch]$EnableTestHooks
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$workspaceRoot = (Resolve-Path (Join-Path $repoRoot "..\..")).Path
$cliRoot = Join-Path $workspaceRoot "tools\arduino-cli-1.5.1"
$cli = Join-Path $cliRoot "arduino-cli.exe"
$configDir = Join-Path $cliRoot "config"
$official = if ($env:SAFE_FIELD_WAVESHARE_SDK) {
    $env:SAFE_FIELD_WAVESHARE_SDK
} else {
    Join-Path $workspaceRoot "tools\waveshare-esp32-s3-touch-amoled-2.06-official"
}
$libraries = Join-Path $official "examples\arduino\libraries"
$output = Join-Path $PSScriptRoot "build"
$work = Join-Path $output "work"
$fqbn = "esp32:esp32:esp32s3:USBMode=hwcdc,CDCOnBoot=cdc,PSRAM=opi,FlashSize=16M,PartitionScheme=app3M_fat9M_16MB"

foreach ($required in @($cli, $configDir, $libraries)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required tool or SDK path not found: $required"
    }
}

$compileArgs = @(
    "--config-dir", $configDir,
    "compile",
    "--fqbn", $fqbn,
    "--libraries", $libraries,
    "--build-path", $work,
    "--output-dir", $output
)
if ($EnableTestHooks) {
    $compileArgs += @("--build-property", "compiler.cpp.extra_flags=-DSAFE_FIELD_ENABLE_TEST_HOOKS=1")
    Write-Warning "Building with serial test hooks enabled. Do not use this artifact operationally."
}
$compileArgs += $PSScriptRoot

& $cli @compileArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$compiledBinary = Join-Path $output "safe_field_operational_v1.ino.bin"
$artifactDir = Join-Path $PSScriptRoot "build_artifacts"
$artifactBinary = Join-Path $artifactDir "safe_field_operational_v1.ino.bin"
if (-not (Test-Path -LiteralPath $compiledBinary)) {
    throw "Compiled application binary not found: $compiledBinary"
}
New-Item -ItemType Directory -Path $artifactDir -Force | Out-Null
Copy-Item -LiteralPath $compiledBinary -Destination $artifactBinary -Force
$artifactHash = (Get-FileHash -LiteralPath $artifactBinary -Algorithm SHA256).Hash
Write-Host "Operational artifact: $artifactBinary"
Write-Host "Operational artifact SHA-256: $artifactHash"

if ($Upload) {
    Write-Warning "Upload was explicitly requested. This sprint's validation command does not use -Upload."
    & $cli --config-dir $configDir upload `
        --fqbn $fqbn `
        --port $Port `
        --input-dir $output `
        $PSScriptRoot
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
