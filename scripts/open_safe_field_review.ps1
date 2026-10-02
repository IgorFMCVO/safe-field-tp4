param(
    [Parameter(Mandatory=$true)][string]$OccurrenceId,
    [Parameter(Mandatory=$true)][string]$CoreUrl,
    [Parameter(Mandatory=$true)][string]$RemoteRepo,
    [Parameter(Mandatory=$true)][string]$CaFile,
    [string]$SshTarget = 'safe-field@safe-field.local',
    [string]$TokenFile = '/home/safe-field/.config/safe-field-runtime/api.token'
)
$ErrorActionPreference = 'Stop'
function Quote-Sh([string]$value) {
    if ($value -notmatch '^[A-Za-z0-9_./:@-]+$') { throw 'Unexpected character in runtime argument.' }
    return "'$value'"
}
$script = $RemoteRepo.TrimEnd('/') + '/scripts/open_safe_field_review.py'
$remote = 'python3 ' + (Quote-Sh $script) + ' --core-url ' + (Quote-Sh $CoreUrl) +
    ' --occurrence-id ' + (Quote-Sh $OccurrenceId) + ' --token-file ' + (Quote-Sh $TokenFile) +
    ' --ca-file ' + (Quote-Sh $CaFile)
# Existing SSH config/key/agent is used. No password or token is embedded here.
$link = (& ssh -o BatchMode=yes -o ConnectTimeout=5 $SshTarget $remote | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Review bootstrap failed. Use the existing authorized SSH session; do not change credentials.' }
$prefix = $CoreUrl.TrimEnd('/') + '/review/bootstrap?ticket='
if (-not $link.StartsWith($prefix) -or $link.Contains("`n") -or $link.Contains("`r")) {
    throw 'Unexpected review response.'
}
Start-Process $link | Out-Null
Write-Output 'REVIEW_OPENED — same occurrence, no operational token entered in browser.'
