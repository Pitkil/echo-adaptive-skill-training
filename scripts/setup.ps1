$ErrorActionPreference = "Stop"

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$VirtualEnvironment = Join-Path $RepositoryRoot ".venv"
$Python = Join-Path $VirtualEnvironment "Scripts\python.exe"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python was not found. Install Python 3.11, 3.12, or 3.13 and add it to PATH."
}

$Version = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($Version -notin @("3.11", "3.12", "3.13")) {
    throw "Python $Version is not supported. Use Python 3.11, 3.12, or 3.13."
}

if (-not (Test-Path -LiteralPath $VirtualEnvironment)) {
    python -m venv $VirtualEnvironment
}

& $Python -m pip install --upgrade pip
& $Python -m pip install -e "$RepositoryRoot[dev]"

$EnvironmentFile = Join-Path $RepositoryRoot ".env"
if (-not (Test-Path -LiteralPath $EnvironmentFile)) {
    Copy-Item -LiteralPath (Join-Path $RepositoryRoot ".env.example") -Destination $EnvironmentFile
}

Write-Host "Environment ready. Configure the model settings in .env, then run scripts\dev.ps1."
