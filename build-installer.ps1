param(
    [string]$CertificateThumbprint = '',
    [string]$TimestampUrl = 'http://timestamp.digicert.com',
    [string]$PythonPath = ''
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$version = '1.0.4'

& .\build.ps1 -PythonPath $PythonPath

$projectPython = $PythonPath
if (-not $projectPython) {
    $projectPython = Join-Path $PSScriptRoot '.venv312\Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $projectPython)) {
    $projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $projectPython)) { $projectPython = 'python' }
$distRoot = 'E:\LAGSHIFT-Builds\public-rc\dist\LAGSHIFT'
$distExe = Join-Path $distRoot 'LAGSHIFT.exe'
if ($CertificateThumbprint) {
    & '.\tools\sign_windows_release.ps1' -CertificateThumbprint $CertificateThumbprint `
        -TimestampUrl $TimestampUrl -Files @($distExe)
    & $projectPython '.\tools\generate_integrity_catalog.py' $distRoot
    if ($LASTEXITCODE -ne 0) { throw 'Post-sign integrity catalog generation failed.' }
    & $projectPython '.\tools\audit_public_archive.py' $distRoot
    if ($LASTEXITCODE -ne 0) { throw 'Post-sign public archive audit failed.' }
}

$candidates = @(
    'E:\LAGSHIFT-Builds\tools\Inno\ISCC.exe',
    'C:\Program Files\Inno Setup 7\ISCC.exe',
    'C:\Program Files (x86)\Inno Setup 7\ISCC.exe',
    'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
    'C:\Program Files\Inno Setup 6\ISCC.exe'
)
$compiler = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $compiler) {
    throw 'Inno Setup 7 is not installed. Install the official signed compiler, then run this script again.'
}

& $compiler '/DBootstrapEngine' '.\installer\LAGSHIFT.iss'
if ($LASTEXITCODE -ne 0) {
    throw "Installer engine compilation failed with exit code $LASTEXITCODE"
}

$engineInstaller = "E:\LAGSHIFT-Builds\engine\LAGSHIFT-$version-Engine.exe"
if ($CertificateThumbprint) {
    & '.\tools\sign_windows_release.ps1' -CertificateThumbprint $CertificateThumbprint `
        -TimestampUrl $TimestampUrl -Files @($engineInstaller)
}

$installerDir = 'E:\LAGSHIFT-Builds\public-rc\installer'
$publicInstaller = Join-Path $installerDir "LAGSHIFT-$version-Setup.exe"

$publishDir = 'E:\LAGSHIFT-Builds\bootstrapper-publish'
$intermediateDir = 'E:\LAGSHIFT-Builds\bootstrapper-obj\'
$binaryDir = 'E:\LAGSHIFT-Builds\bootstrapper-bin\'
New-Item -ItemType Directory -Force -Path $publishDir | Out-Null
dotnet publish '.\installer\bootstrapper\Lagshift.Setup.csproj' -c Release -o $publishDir --nologo `
    -p:BaseIntermediateOutputPath=$intermediateDir -p:BaseOutputPath=$binaryDir
if ($LASTEXITCODE -ne 0) {
    throw "Custom installer compilation failed with exit code $LASTEXITCODE"
}

$bootstrapper = Join-Path $publishDir "LAGSHIFT-$version-Setup.exe"
if (-not (Test-Path -LiteralPath $bootstrapper)) {
    throw 'Custom installer output was not created.'
}
Copy-Item -LiteralPath $bootstrapper -Destination $publicInstaller -Force
Copy-Item -LiteralPath $bootstrapper -Destination (Join-Path $installerDir "LAGSHIFT-$version-Setup-SelfContained.exe") -Force

$lightIntermediateDir = 'E:\LAGSHIFT-Builds\bootstrapper-light-obj\'
$lightBinaryDir = 'E:\LAGSHIFT-Builds\bootstrapper-light-bin\'
dotnet build '.\installer\bootstrapper\Lagshift.Setup.Framework.csproj' -c Release --nologo `
    -p:BaseIntermediateOutputPath=$lightIntermediateDir -p:BaseOutputPath=$lightBinaryDir
if ($LASTEXITCODE -ne 0) {
    throw "Lightweight installer compilation failed with exit code $LASTEXITCODE"
}
$lightInstaller = Join-Path $lightBinaryDir "Release\net48\LAGSHIFT-$version-Setup-Light.exe"
Copy-Item -LiteralPath $lightInstaller -Destination (Join-Path $installerDir "LAGSHIFT-$version-Setup-Light.exe") -Force

if ($CertificateThumbprint) {
    & '.\tools\sign_windows_release.ps1' -CertificateThumbprint $CertificateThumbprint `
        -TimestampUrl $TimestampUrl -Files @(
            $publicInstaller,
            (Join-Path $installerDir "LAGSHIFT-$version-Setup-SelfContained.exe"),
            (Join-Path $installerDir "LAGSHIFT-$version-Setup-Light.exe")
        )
}

& '.\tools\write_release_checksums.ps1' -InstallerDirectory $installerDir -Version $version
Copy-Item -LiteralPath '.\SHA256SUMS.txt' `
    -Destination (Join-Path $installerDir 'SHA256SUMS.txt') -Force

Write-Host "Custom installer ready: E:\LAGSHIFT-Builds\public-rc\installer\LAGSHIFT-$version-Setup.exe"
Write-Host "Lightweight installer ready: E:\LAGSHIFT-Builds\public-rc\installer\LAGSHIFT-$version-Setup-Light.exe"
Write-Host "Self-contained installer ready: E:\LAGSHIFT-Builds\public-rc\installer\LAGSHIFT-$version-Setup-SelfContained.exe"
