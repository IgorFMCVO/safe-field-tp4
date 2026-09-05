param([string]$Port = "COM7")

$ErrorActionPreference = "Stop"
$ssid = $env:SAFE_FIELD_WIFI_SSID
$password = $env:SAFE_FIELD_WIFI_PASSWORD
$coreUrl = $env:SAFE_FIELD_CORE_URL

if ([string]::IsNullOrWhiteSpace($ssid) -or
    [string]::IsNullOrWhiteSpace($password) -or
    [string]::IsNullOrWhiteSpace($coreUrl)) {
    throw "Set SAFE_FIELD_WIFI_SSID, SAFE_FIELD_WIFI_PASSWORD and SAFE_FIELD_CORE_URL in the current process. They are never written to the repository."
}

$serial = [System.IO.Ports.SerialPort]::new($Port, 115200, "None", 8, "One")
$serial.NewLine = "`n"
try {
    $serial.Open()
    Start-Sleep -Milliseconds 500
    $serial.WriteLine("SET_WIFI $ssid`t$password")
    Start-Sleep -Milliseconds 250
    $serial.WriteLine("SET_CORE $coreUrl")
    Start-Sleep -Milliseconds 250
    $serial.WriteLine("SHOW_CONFIG")
    Start-Sleep -Seconds 2
    $output = $serial.ReadExisting()
    $output -replace '(?i)(password=)[^\s]+', '$1REDACTED'
} finally {
    if ($serial.IsOpen) { $serial.Close() }
    $serial.Dispose()
}
