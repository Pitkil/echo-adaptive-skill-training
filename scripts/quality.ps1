$ErrorActionPreference = "Stop"

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Virtual environment not found. Run scripts\setup.ps1 first."
}

Push-Location $RepositoryRoot
try {
    & $Python -m ruff check apps/api/integrations services tests/unit tests/integration
    & $Python -m compileall -q apps/api services
}
finally {
    Pop-Location
}
