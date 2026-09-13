$ErrorActionPreference = 'Stop'

$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$output = Join-Path $root 'Igor_Monteiro_PB_TP5.ZIP'
$include = @(
    'README_TP5.md',
    '.gitattributes',
    '.gitignore',
    '.github',
    'scripts',
    'verilog_tp5',
    'assembly_tp5',
    'docs_tp5'
)
$excludedSegments = @('__pycache__', '.pytest_cache', '.mypy_cache', '.venv', 'venv', 'node_modules', 'preview')

if (Test-Path -LiteralPath $output) {
    Remove-Item -LiteralPath $output -Force
}

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$stream = [System.IO.File]::Open($output, [System.IO.FileMode]::CreateNew)
$archive = [System.IO.Compression.ZipArchive]::new($stream, [System.IO.Compression.ZipArchiveMode]::Create)

try {
    foreach ($item in $include) {
        $source = Join-Path $root $item
        if (-not (Test-Path -LiteralPath $source)) {
            throw "Required package input is missing: $item"
        }

        $files = if (Test-Path -LiteralPath $source -PathType Leaf) {
            @(Get-Item -LiteralPath $source)
        } else {
            @(Get-ChildItem -LiteralPath $source -Recurse -File)
        }

        foreach ($file in $files) {
            $relative = [System.IO.Path]::GetRelativePath($root, $file.FullName).Replace('\', '/')
            $segments = $relative.Split('/')
            if ($segments | Where-Object { $excludedSegments -contains $_ }) { continue }
            if ($file.Name -match '\.(tmp|bak|swp|pyc)$') { continue }
            if ($file.Name -eq '.env' -or $file.Name -like '.env.*') { continue }
            if ($relative -eq 'Igor_Monteiro_PB_TP5.ZIP') { continue }

            [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                $archive,
                $file.FullName,
                $relative,
                [System.IO.Compression.CompressionLevel]::Optimal
            ) | Out-Null
        }
    }
}
finally {
    $archive.Dispose()
    $stream.Dispose()
}

$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $output).Hash
Write-Output "ZIP=$output"
Write-Output "SHA256=$hash"
