param(
    [switch]$AllowInsecureDevelopment
)

$ErrorActionPreference = "Stop"

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"
$ServiceRoot = Join-Path $RepositoryRoot "services\simplemem"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Virtual environment not found. Run scripts\setup.ps1 first."
}

if (-not $env:SIMPLEMEM_DB_PATH) {
    $env:SIMPLEMEM_DB_PATH = Join-Path $RepositoryRoot "data\simplemem.db"
}
if (-not $env:SIMPLEMEM_HOST) {
    $env:SIMPLEMEM_HOST = "127.0.0.1"
}
if (-not $env:SIMPLEMEM_PORT) {
    $env:SIMPLEMEM_PORT = "8020"
}
if (-not $env:SIMPLEMEM_API_KEY) {
    if (-not $AllowInsecureDevelopment) {
        throw "Set SIMPLEMEM_API_KEY, or pass -AllowInsecureDevelopment for loopback-only local use."
    }
    if ($env:SIMPLEMEM_HOST -ne "127.0.0.1" -and $env:SIMPLEMEM_HOST -ne "localhost") {
        throw "Insecure development mode must bind SIMPLEMEM_HOST to 127.0.0.1 or localhost."
    }
    $env:SIMPLEMEM_ALLOW_INSECURE_DEV = "true"
}

$env:PYTHONPATH = $ServiceRoot
& $Python -m simplemem
