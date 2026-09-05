param(
    [string]$Port = "COM7",
    [switch]$Upload
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
$fqbn = "esp32:esp32:esp32s3:USBMode=hwcdc,CDCOnBoot=cdc,PSRAM=opi,FlashSize=16M,PartitionScheme=app3M_fat9M_16MB"

foreach ($required in @($cli, $configDir, $libraries, (Join-Path $PSScriptRoot "safe_field_speech_pcm.h"))) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Required path not found: $required" }
}

& $cli --config-dir $configDir compile --fqbn $fqbn --libraries $libraries `
    --output-dir $output $PSScriptRoot
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ($Upload) {
    & $cli --config-dir $configDir upload --fqbn $fqbn --port $Port `
        --input-dir $output $PSScriptRoot
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
