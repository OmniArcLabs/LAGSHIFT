param(
    [string]$PythonPath = ''
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$releaseRoot = 'E:\LAGSHIFT-Builds\public-rc'
$distPath = Join-Path $releaseRoot 'dist'
$workPath = Join-Path $releaseRoot 'work'
New-Item -ItemType Directory -Force -Path $distPath | Out-Null
New-Item -ItemType Directory -Force -Path $workPath | Out-Null
$projectPython = $PythonPath
if (-not $projectPython) {
    $projectPython = Join-Path $PSScriptRoot '.venv312\Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $projectPython)) {
    $projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $projectPython)) {
    $projectPython = 'python'
}
& $projectPython -c "import sys, PySide6, shiboken6; assert sys.version_info[:2] == (3, 12), 'Release Python must be 3.12'; assert PySide6.__version__ == '6.8.3', 'PySide6 must be 6.8.3'; assert shiboken6.__version__ == '6.8.3', 'shiboken6 must be 6.8.3'"
if ($LASTEXITCODE -ne 0) {
    throw 'Release dependency versions do not match the pinned runtime.'
}
& $projectPython -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) {
    throw "Test suite failed with exit code $LASTEXITCODE"
}
& $projectPython -m PyInstaller --noconfirm --clean --distpath $distPath --workpath $workPath LAGSHIFT.spec
if ($LASTEXITCODE -ne 0) {
    throw "Application build failed with exit code $LASTEXITCODE"
}
$translationsPath = Join-Path $distPath 'LAGSHIFT\_internal\PySide6\translations'
if (Test-Path -LiteralPath $translationsPath) {
    Get-ChildItem -LiteralPath $translationsPath -Filter '*.qm' -File |
        Where-Object { $_.Name -notmatch '(_fa|_en)\.qm$' } |
        Remove-Item -Force
}
& $projectPython '.\tools\generate_integrity_catalog.py' (Join-Path $distPath 'LAGSHIFT')
if ($LASTEXITCODE -ne 0) {
    throw "Integrity catalog generation failed with exit code $LASTEXITCODE"
}
& $projectPython '.\tools\audit_public_archive.py' (Join-Path $distPath 'LAGSHIFT')
if ($LASTEXITCODE -ne 0) {
    throw "Public archive audit failed with exit code $LASTEXITCODE"
}
Write-Host "Build ready: $distPath\LAGSHIFT\LAGSHIFT.exe"
