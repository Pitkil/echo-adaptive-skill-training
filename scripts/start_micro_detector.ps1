param(
    [string]$PythonPath = "python",
    [string]$ModelRoot = "",
    [int]$Port = 8030
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($ModelRoot)) {
    $ModelRoot = Join-Path $repositoryRoot "models\micro_detector"
}

$requiredPaths = @(
    (Join-Path $ModelRoot "wavlm-base-plus\config.json"),
    (Join-Path $ModelRoot "wavlm-base-plus\preprocessor_config.json"),
    (Join-Path $ModelRoot "wavlm-base-plus\model.safetensors"),
    (Join-Path $ModelRoot "behavior_prototypes.pt"),
    (Join-Path $repositoryRoot "services\micro_detector_real\app.py")
)

foreach ($requiredPath in $requiredPaths) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Required micro-detector file not found: $requiredPath"
    }
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    throw "Required micro-detector executable not found: ffmpeg"
}

$env:MICRO_MODEL_ROOT = (Resolve-Path -LiteralPath $ModelRoot).Path
$env:MICRO_DETECTOR_OFFLINE_MODE = "true"
Push-Location $repositoryRoot
try {
    & $PythonPath -m uvicorn `
        services.micro_detector_real.app:app `
        --host 127.0.0.1 `
        --port $Port
}
finally {
    Pop-Location
}
