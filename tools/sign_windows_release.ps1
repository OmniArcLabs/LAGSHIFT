param(
    [Parameter(Mandatory = $true)][string]$CertificateThumbprint,
    [Parameter(Mandatory = $true)][string[]]$Files,
    [string]$TimestampUrl = 'http://timestamp.digicert.com'
)

$ErrorActionPreference = 'Stop'
$certificate = Get-ChildItem -Path Cert:\CurrentUser\My, Cert:\LocalMachine\My |
    Where-Object { $_.Thumbprint -eq $CertificateThumbprint -and $_.HasPrivateKey } |
    Select-Object -First 1
if (-not $certificate) { throw 'A matching code-signing certificate with a private key was not found.' }
if (-not ($certificate.EnhancedKeyUsageList.ObjectId -contains '1.3.6.1.5.5.7.3.3')) {
    throw 'The selected certificate is not valid for code signing.'
}

$kits = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\bin'
$signtool = Get-ChildItem -LiteralPath $kits -Filter signtool.exe -Recurse -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match '\\x64\\signtool\.exe$' } |
    Sort-Object FullName -Descending | Select-Object -First 1
if (-not $signtool) { throw 'signtool.exe was not found in the Windows SDK.' }

foreach ($file in $Files) {
    $resolved = (Resolve-Path -LiteralPath $file).Path
    if ([IO.Path]::GetExtension($resolved) -notin '.exe', '.dll', '.msi') {
        throw "Unsupported signing target: $resolved"
    }
    & $signtool.FullName sign /sha1 $CertificateThumbprint /fd SHA256 /tr $TimestampUrl /td SHA256 $resolved
    if ($LASTEXITCODE -ne 0) { throw "Signing failed: $resolved" }
    & $signtool.FullName verify /pa /all $resolved
    if ($LASTEXITCODE -ne 0) { throw "Signature verification failed: $resolved" }
}
