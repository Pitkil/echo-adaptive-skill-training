param(
    [string]$ModelRoot = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($ModelRoot)) {
    $ModelRoot = Join-Path $repositoryRoot "models\micro_detector"
}
$resolvedModelRoot = (Resolve-Path -LiteralPath $ModelRoot).Path
$checksumPath = Join-Path $resolvedModelRoot "SHA256SUMS.txt"
if (-not (Test-Path -LiteralPath $checksumPath -PathType Leaf)) {
    throw "Model checksum manifest not found: $checksumPath"
}

$checked = 0
foreach ($line in Get-Content -LiteralPath $checksumPath) {
    if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith("#")) {
        continue
    }
    if ($line -notmatch '^([0-9a-fA-F]{64})\s{2}(.+)$') {
        throw "Invalid checksum line: $line"
    }
    $expectedHash = $Matches[1].ToLowerInvariant()
    $relativePath = $Matches[2].Replace("/", [IO.Path]::DirectorySeparatorChar)
    $artifactPath = Join-Path $resolvedModelRoot $relativePath
    if (-not (Test-Path -LiteralPath $artifactPath -PathType Leaf)) {
        throw "Required model artifact not found: $artifactPath"
    }
    $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $artifactPath).Hash.ToLowerInvariant()
    if ($actualHash -ne $expectedHash) {
        throw "Model artifact checksum mismatch: $relativePath"
    }
    $checked += 1
}

$weightPath = Join-Path $resolvedModelRoot "wavlm-base-plus\model.safetensors"
if ((Get-Item -LiteralPath $weightPath).Length -lt 300MB) {
    throw "WavLM weight is missing or is only a Git LFS pointer: $weightPath"
}

Write-Host "Verified $checked offline model artifacts at $resolvedModelRoot"
