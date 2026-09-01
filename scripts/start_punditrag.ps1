[CmdletBinding()]
param(
    [Parameter()]
    [string]$PunditRAGRoot = $env:PUNDITRAG_ROOT,

    [Parameter()]
    [switch]$Build,

    [Parameter()]
    [ValidateRange(30, 600)]
    [int]$TimeoutSeconds = 240
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($PunditRAGRoot)) {
    throw "Specify the PunditRAG repository with -PunditRAGRoot or PUNDITRAG_ROOT."
}

$resolvedRoot = (Resolve-Path -LiteralPath $PunditRAGRoot).Path
$composeFile = Join-Path $resolvedRoot "docker-compose.yml"
$environmentFile = Join-Path $resolvedRoot ".env.docker"

if (-not (Test-Path -LiteralPath $composeFile -PathType Leaf)) {
    throw "PunditRAG Compose file was not found: $composeFile"
}
if (-not (Test-Path -LiteralPath $environmentFile -PathType Leaf)) {
    throw "PunditRAG environment file was not found: $environmentFile. Create it from that repository's instructions; never commit secrets."
}

& docker version | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Docker Engine is unavailable. Run scripts\\ensure_docker.ps1 first."
}

$composeArgs = @("compose", "--project-directory", $resolvedRoot, "--env-file", $environmentFile, "-f", $composeFile, "up", "-d")
if ($Build) {
    $composeArgs += "--build"
}
else {
    # A normal team startup must not recreate an existing app container merely
    # because a local Compose environment file has changed. That can make the
    # app credentials disagree with already-initialized MongoDB/MinIO volumes.
    $composeArgs += "--no-recreate"
}

Write-Host "Starting PunditRAG from $resolvedRoot ..."
& docker @composeArgs
if ($LASTEXITCODE -ne 0) {
    throw "PunditRAG did not start. Run docker compose logs app from its repository directory."
}

$endAt = (Get-Date).AddSeconds($TimeoutSeconds)
$healthUrls = @("http://127.0.0.1:8000/health", "http://127.0.0.1:8001/health")
do {
    $allHealthy = $true
    foreach ($healthUrl in $healthUrls) {
        try {
            $response = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 5
            if ($response.status -ne "ok") {
                $allHealthy = $false
            }
        }
        catch {
            $allHealthy = $false
        }
    }

    if ($allHealthy) {
        Write-Host "PunditRAG is ready: import http://127.0.0.1:8000, query http://127.0.0.1:8001"
        exit 0
    }
    Start-Sleep -Seconds 3
} while ((Get-Date) -lt $endAt)

throw "PunditRAG did not pass both 8000/8001 health checks within $TimeoutSeconds seconds. Run docker compose logs app in $resolvedRoot."
