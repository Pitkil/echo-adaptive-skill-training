param(
    [switch]$UseOfflineImages
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$baseCompose = Join-Path $repositoryRoot "docker-compose.yml"
$competitionCompose = Join-Path $repositoryRoot "docker-compose.competition.yml"
$environmentFile = Join-Path $repositoryRoot ".env"

function Get-EnvironmentFileValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $null
    }
    $escapedName = [Regex]::Escape($Name)
    $line = Get-Content -LiteralPath $Path |
        Where-Object { $_ -match "^\s*$escapedName\s*=" } |
        Select-Object -Last 1
    if ($null -eq $line) {
        return $null
    }
    $value = ($line -split "=", 2)[1].Trim()
    if ($value.Length -ge 2) {
        $first = $value.Substring(0, 1)
        $last = $value.Substring($value.Length - 1, 1)
        if (($first -eq '"' -and $last -eq '"') -or ($first -eq "'" -and $last -eq "'")) {
            $value = $value.Substring(1, $value.Length - 2)
        }
    }
    return $value
}

$simpleMemApiKey = $env:SIMPLEMEM_API_KEY
if ([string]::IsNullOrWhiteSpace($simpleMemApiKey)) {
    $simpleMemApiKey = Get-EnvironmentFileValue -Path $environmentFile -Name "SIMPLEMEM_API_KEY"
}
if ([string]::IsNullOrWhiteSpace($simpleMemApiKey) -or
    [Text.Encoding]::UTF8.GetByteCount($simpleMemApiKey) -lt 32) {
    throw "SIMPLEMEM_API_KEY must contain at least 32 UTF-8 bytes. Copy .env.example to .env and set a strong random key before starting the competition stack."
}

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
