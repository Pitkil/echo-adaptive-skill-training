# scripts/ensure_docker.ps1
# 一键自检并恢复 Docker Desktop 运行时（长期维护入口）
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File scripts\ensure_docker.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\ensure_docker.ps1 -Force
#
# -Force 表示：常规启动后 daemon 仍不可用时，做一次受控重启（仅重启运行时，不删数据）。
#
# 红线（与 AGENTS.md 一致）：
#   - 只恢复 Docker Desktop / WSL 运行时，绝不删除或重置数据盘。
#   - 不执行 "Reset to factory defaults"，不清理 D:\DockerDesktopData。
#   - 幂等：Docker 正常时直接 PASS，不做多余动作。

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

# ---- 1. 检查 docker CLI 是否可用 ----
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Fail "docker CLI 不在 PATH 中，请确认 Docker Desktop 已安装。"
    exit 1
}

# ---- 2. 检查 daemon 是否已可连接 ----
function Test-DockerDaemon {
    $server = & docker version --format '{{.Server.Version}}' 2>$null
    return ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($server))
}

if (Test-DockerDaemon) {
    Write-Ok "Docker daemon 已可连接 (Server: $(docker version --format '{{.Server.Version}}' 2>$null))"
    & docker ps --format 'table {{.Names}}\t{{.Status}}'
    Write-Step "无需修复，直接退出。"
    exit 0
}

Write-Warn "Docker daemon 不可连接，开始尝试恢复（不会删除任何数据）。"

# ---- 3. 尝试启动 Docker Desktop ----
if (Test-Path -LiteralPath $DockerDesktopExe) {
    if (-not (Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue)) {
        Write-Step "启动 Docker Desktop: $DockerDesktopExe"
        Start-Process -FilePath $DockerDesktopExe
    }
}
else {
    Write-Warn "未找到 $DockerDesktopExe，尝试按 PATH 查找 Docker Desktop。"
    $found = Get-Command "Docker Desktop.exe" -ErrorAction SilentlyContinue
    if ($found) {
        Start-Process -FilePath $found.Source
    }
    else {
        Write-Fail "找不到 Docker Desktop。请先确认安装目录，或重装并固定安装路径。"
        exit 1
    }
}

# ---- 4. 等待 daemon 恢复（含可选受控重启） ----
$deadline = (Get-Date).AddSeconds($MaxWaitSeconds)
while ((Get-Date) -lt $deadline) {
    if (Test-DockerDaemon) { break }
    Start-Sleep -Seconds $PollIntervalSeconds
}

if (-not (Test-DockerDaemon) -and $Force) {
    Write-Warn "常规启动后 daemon 仍不可用，执行受控重启（仅重启运行时，不删数据）。"
    Get-Process -Name "Docker Desktop", "com.docker.backend" -ErrorAction SilentlyContinue |
        Stop-Process -Force -ErrorAction SilentlyContinue
    & wsl --shutdown
    Start-Sleep -Seconds 5
    Start-Process -FilePath $DockerDesktopExe
    $deadline = (Get-Date).AddSeconds($MaxWaitSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-DockerDaemon) { break }
        Start-Sleep -Seconds $PollIntervalSeconds
    }
}

if (-not (Test-DockerDaemon)) {
    Write-Fail "Docker daemon 在 $MaxWaitSeconds 秒内未能恢复。"
    Write-Fail "下一步（人工）:"
    Write-Fail "  wsl --shutdown"
    Write-Fail "  重新启动 Docker Desktop"
    Write-Fail "切勿执行 Reset to factory defaults；数据盘位于 D:\DockerDesktopData，不要清理。"
    exit 1
}

Write-Ok "Docker daemon 已恢复。"
& docker version
& docker ps --format 'table {{.Names}}\t{{.Status}}'
Write-Step "完成。现在可以启动项目服务栈。"
