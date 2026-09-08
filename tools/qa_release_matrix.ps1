param(
    [Parameter(Mandatory = $true)][string]$Executable,
    [Parameter(Mandatory = $true)][string]$OutputFile,
    [Parameter(Mandatory = $true)][string]$TestRoot
)

$ErrorActionPreference = 'Stop'
$exe = (Resolve-Path -LiteralPath $Executable).Path
$root = [IO.Path]::GetFullPath($TestRoot)
New-Item -ItemType Directory -Path $root -Force | Out-Null
$results = @()

foreach ($scale in @('1', '1.25', '1.5', '2')) {
    $profile = Join-Path $root ('scale-' + $scale.Replace('.', '-'))
    $roaming = Join-Path $profile 'Roaming'
    $local = Join-Path $profile 'Local'
    New-Item -ItemType Directory -Path $roaming, $local -Force | Out-Null
    $start = New-Object System.Diagnostics.ProcessStartInfo
    $start.FileName = $exe
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.EnvironmentVariables['APPDATA'] = $roaming
    $start.EnvironmentVariables['LOCALAPPDATA'] = $local
    $start.EnvironmentVariables['QT_SCALE_FACTOR'] = $scale
    $process = [Diagnostics.Process]::Start($start)
    Start-Sleep -Seconds 8
    $alive = -not $process.HasExited
    $responsive = if ($alive) { $process.Responding } else { $false }
    if ($alive) {
        $process.Kill()
        $process.WaitForExit(5000) | Out-Null
        # Give Qt/Windows time to release the single-instance lock before the
        # next DPI launch. Without this pause the fourth launch can be rejected
        # even though it runs correctly in isolation.
        Start-Sleep -Milliseconds 1200
    }
    $results += [ordered]@{ scale = $scale; alive = $alive; responsive = $responsive }
}

$gpu = @(Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue |
    ForEach-Object { [ordered]@{ name = $_.Name; driver = $_.DriverVersion } })
$defender = try {
    $status = Get-MpComputerStatus -ErrorAction Stop
    [ordered]@{ available = $true; antivirus_enabled = $status.AntivirusEnabled; realtime = $status.RealTimeProtectionEnabled }
} catch {
    [ordered]@{ available = $false; antivirus_enabled = $false; realtime = $false }
}
$signature = Get-AuthenticodeSignature -LiteralPath $exe
$document = [ordered]@{
    tested_at = [DateTimeOffset]::UtcNow.ToString('o')
    executable = $exe
    os = [Environment]::OSVersion.VersionString
    windows_build = (Get-CimInstance Win32_OperatingSystem).BuildNumber
    gpu = $gpu
    defender = $defender
    authenticode = $signature.Status.ToString()
    dpi_smoke = $results
}
$destination = [IO.Path]::GetFullPath($OutputFile)
New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($destination)) -Force | Out-Null
$document | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $destination -Encoding utf8
$document | ConvertTo-Json -Depth 6
if ($results.Where({ -not $_.alive -or -not $_.responsive }).Count -gt 0) { exit 2 }
