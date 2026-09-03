# scripts/ensure_docker.ps1
# Idempotently check and recover Docker Desktop without deleting runtime data.
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File scripts\ensure_docker.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\ensure_docker.ps1 -Force
#
# -Force performs one controlled runtime restart if an ordinary start fails.
#
# This script never resets Docker Desktop or deletes D:\DockerDesktopData.

param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$DockerDesktopExe = "D:\Docker\Docker\Docker Desktop.exe"
$MaxWaitSeconds = 120
$PollIntervalSeconds = 5

function Write-Step { param([string]$Message) Write-Host "[ensure-docker] $Message" }
function Write-Ok    { param([string]$Message) Write-Host "[ensure-docker][OK] $Message" }
function Write-Warn  { param([string]$Message) Write-Host "[ensure-docker][WARN] $Message" }
function Write-Fail  { param([string]$Message) Write-Host "[ensure-docker][FAIL] $Message" }

# ---- 1. Check the Docker CLI ----
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Fail "docker CLI is not available in PATH."
    exit 1
}

# ---- 2. Check the daemon ----
function Test-DockerDaemon {
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    $server = & docker version --format '{{.Server.Version}}' 2>$null
    $dockerExitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorActionPreference
    return ($dockerExitCode -eq 0 -and -not [string]::IsNullOrWhiteSpace($server))
}

if (Test-DockerDaemon) {
    Write-Ok "Docker daemon is reachable (Server: $(docker version --format '{{.Server.Version}}' 2>$null))."
    & docker ps --format 'table {{.Names}}\t{{.Status}}'
    Write-Step "No recovery was needed."
    exit 0
}

Write-Warn "Docker daemon is unreachable. Starting safe recovery; no data will be deleted."

# ---- 3. Start Docker Desktop if needed ----
if (Test-Path -LiteralPath $DockerDesktopExe) {
    if (-not (Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue)) {
        Write-Step "Starting Docker Desktop from $DockerDesktopExe."
        Start-Process -FilePath $DockerDesktopExe -WindowStyle Hidden
    }
}
else {
    Write-Warn "Docker Desktop was not found at $DockerDesktopExe; checking PATH."
    $found = Get-Command "Docker Desktop.exe" -ErrorAction SilentlyContinue
    if ($found) {
        Start-Process -FilePath $found.Source -WindowStyle Hidden
    }
    else {
        Write-Fail "Docker Desktop executable was not found."
        exit 1
    }
}

# ---- 4. Wait for recovery and optionally restart the runtime ----
$deadline = (Get-Date).AddSeconds($MaxWaitSeconds)
while ((Get-Date) -lt $deadline) {
    if (Test-DockerDaemon) { break }
    Start-Sleep -Seconds $PollIntervalSeconds
}

if (-not (Test-DockerDaemon) -and $Force) {
    Write-Warn "Ordinary startup failed. Restarting only the Docker and WSL runtime."
    Get-Process -Name "Docker Desktop", "com.docker.backend" -ErrorAction SilentlyContinue |
        Stop-Process -Force -ErrorAction SilentlyContinue
    & wsl --shutdown
    Start-Sleep -Seconds 5
    Start-Process -FilePath $DockerDesktopExe -WindowStyle Hidden
    $deadline = (Get-Date).AddSeconds($MaxWaitSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-DockerDaemon) { break }
        Start-Sleep -Seconds $PollIntervalSeconds
    }
}

if (-not (Test-DockerDaemon)) {
    Write-Fail "Docker daemon did not recover within $MaxWaitSeconds seconds."
    Write-Fail "Do not use Reset to factory defaults or delete D:\DockerDesktopData."
    exit 1
}

Write-Ok "Docker daemon recovered."
& docker version
& docker ps --format 'table {{.Names}}\t{{.Status}}'
Write-Step "Recovery complete."
