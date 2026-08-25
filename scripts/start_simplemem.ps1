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
    $env:SIMPLEMEM_HOST = "0.0.0.0"
}
if (-not $env:SIMPLEMEM_PORT) {
    $env:SIMPLEMEM_PORT = "8020"
}

$env:PYTHONPATH = $ServiceRoot
& $Python -m simplemem
