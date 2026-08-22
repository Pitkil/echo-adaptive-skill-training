param(
    [string]$SpeechProjectRoot = "D:\SpeechProject",
    [int]$Port = 8030
)

$ErrorActionPreference = "Stop"
$pythonPath = Join-Path $SpeechProjectRoot "venv\Scripts\python.exe"
$pipelinePath = Join-Path $SpeechProjectRoot "pipeline.py"
$detectionUtilsPath = Join-Path $SpeechProjectRoot "detection_utils.py"
$step3Path = Join-Path $SpeechProjectRoot "step3.py"
$prototypePath = Join-Path $SpeechProjectRoot "prototypes\behavior_prototypes.pt"
$servicePath = Join-Path (Split-Path -Parent $PSScriptRoot) "services\micro_detector_real\app.py"

foreach ($requiredPath in @($pythonPath, $pipelinePath, $detectionUtilsPath, $step3Path, $prototypePath, $servicePath)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Required micro-detector file not found: $requiredPath"
    }
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    throw "Required micro-detector executable not found: ffmpeg"
}

$env:SPEECH_PROJECT_ROOT = (Resolve-Path -LiteralPath $SpeechProjectRoot).Path
$env:MICRO_DETECTOR_OFFLINE_MODE = "true"
& $pythonPath -m uvicorn `
    --app-dir (Split-Path -Parent $servicePath) `
    app:app `
    --host 127.0.0.1 `
    --port $Port
