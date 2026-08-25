param(
    [switch]$UseOfflineImages
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$baseCompose = Join-Path $repositoryRoot "docker-compose.yml"
$competitionCompose = Join-Path $repositoryRoot "docker-compose.competition.yml"

& (Join-Path $PSScriptRoot "verify_micro_model.ps1")

if ($UseOfflineImages) {
    $imageArchive = Join-Path $repositoryRoot "offline-images\echo-competition-images.tar"
    if (-not (Test-Path -LiteralPath $imageArchive -PathType Leaf)) {
        throw "Offline image archive not found: $imageArchive"
    }
    $checksumManifest = Join-Path $repositoryRoot "offline-images\SHA256SUMS.txt"
    if (-not (Test-Path -LiteralPath $checksumManifest -PathType Leaf)) {
        throw "Offline image checksum manifest not found: $checksumManifest"
    }
    $checksumLine = (Get-Content -LiteralPath $checksumManifest | Select-Object -First 1)
    if ($checksumLine -notmatch '^([0-9a-fA-F]{64})\s{2}echo-competition-images\.tar$') {
        throw "Invalid offline image checksum manifest: $checksumManifest"
    }
    $expectedHash = $Matches[1].ToLowerInvariant()
    $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $imageArchive).Hash.ToLowerInvariant()
    if ($actualHash -ne $expectedHash) {
        throw "Offline image archive checksum mismatch: $imageArchive"
    }
    docker load --input $imageArchive
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to load offline Docker images"
    }
    docker compose -f $baseCompose -f $competitionCompose up --detach --no-build
}
else {
    docker compose -f $baseCompose -f $competitionCompose up --build --detach
}
if ($LASTEXITCODE -ne 0) {
    throw "Competition services failed to start"
}
