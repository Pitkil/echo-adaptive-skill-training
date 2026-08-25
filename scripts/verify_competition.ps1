param(
    [int]$Port = 8030
)

$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot "verify_micro_model.ps1")
if ($LASTEXITCODE -ne 0) {
    throw "Offline model verification failed"
}

$healthUrl = "http://127.0.0.1:$Port/health"
$health = Invoke-RestMethod -Method Get -Uri $healthUrl -TimeoutSec 10
if ($health.status -ne "ok" -or $health.mode -ne "real") {
    throw "Detector health check did not report real mode: $($health | ConvertTo-Json -Compress)"
}
if ([string]::IsNullOrWhiteSpace($health.detector_version)) {
    throw "Detector health check omitted detector_version"
}
Write-Host "Real detector ready: $($health.detector_version)"
