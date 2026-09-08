param(
    [string]$InstallerDirectory = 'E:\LAGSHIFT-Builds\public-rc\installer',
    [string]$OutputFile = (Join-Path $PSScriptRoot '..\SHA256SUMS.txt')
)

$ErrorActionPreference = 'Stop'
$names = @(
    'LAGSHIFT-1.0.0-Setup.exe',
    'LAGSHIFT-1.0.0-Setup-Light.exe'
)

$lines = foreach ($name in $names) {
    $path = Join-Path $InstallerDirectory $name
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Release artifact was not found: $path"
    }
    $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
    "$hash  $name"
}

[System.IO.File]::WriteAllLines(
    [System.IO.Path]::GetFullPath($OutputFile),
    $lines,
    [System.Text.UTF8Encoding]::new($false)
)
Write-Host "Release checksums written to $OutputFile"
