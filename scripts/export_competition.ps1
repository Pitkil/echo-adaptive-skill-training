param(
    [string]$OutputDirectory = "",
    [string]$Ref = "HEAD",
    [switch]$IncludeDockerImages
)

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $repositoryRoot "dist\ECHO-competition"
}
$outputParent = Split-Path -Parent $OutputDirectory
New-Item -ItemType Directory -Force -Path $outputParent | Out-Null
$resolvedOutputParent = (Resolve-Path -LiteralPath $outputParent).Path
$outputLeaf = Split-Path -Leaf $OutputDirectory
$resolvedOutput = Join-Path $resolvedOutputParent $outputLeaf
if (-not $resolvedOutput.StartsWith($repositoryRoot + [IO.Path]::DirectorySeparatorChar)) {
    throw "Output directory must stay inside the repository workspace: $resolvedOutput"
}
if (Test-Path -LiteralPath $resolvedOutput) {
    throw "Output directory already exists; choose a new empty destination: $resolvedOutput"
}

$status = git -C $repositoryRoot status --porcelain
if ($LASTEXITCODE -ne 0 -or $status) {
    throw "Export requires a clean Git worktree"
}
git -C $repositoryRoot lfs fsck
if ($LASTEXITCODE -ne 0) {
    throw "Git LFS verification failed"
}
& (Join-Path $PSScriptRoot "verify_micro_model.ps1")
if ($LASTEXITCODE -ne 0) {
    throw "Offline model verification failed"
}

$archivePath = Join-Path $resolvedOutputParent "$outputLeaf-source.zip"
if (Test-Path -LiteralPath $archivePath) {
    throw "Temporary archive already exists: $archivePath"
}
git -C $repositoryRoot archive --format=zip --output=$archivePath $Ref
if ($LASTEXITCODE -ne 0) {
    throw "Failed to export Git source archive"
}
Expand-Archive -LiteralPath $archivePath -DestinationPath $resolvedOutput
Remove-Item -LiteralPath $archivePath

# Git archives contain LFS pointer blobs. Overwrite only the frozen model tree
# with verified working-tree artifacts so the submission is actually offline.
$exportedModels = Join-Path $resolvedOutput "models\micro_detector"
New-Item -ItemType Directory -Force -Path $exportedModels | Out-Null
Copy-Item -Path (Join-Path $repositoryRoot "models\micro_detector\*") `
    -Destination $exportedModels -Recurse -Force

$commit = git -C $repositoryRoot rev-parse $Ref
$manifest = @(
    "ECHO competition delivery",
    "source_ref=$Ref",
    "source_commit=$commit",
    "exported_at=$([DateTimeOffset]::Now.ToString('o'))",
    "model_manifest=models/micro_detector/SHA256SUMS.txt"
)
Set-Content -LiteralPath (Join-Path $resolvedOutput "DELIVERY-MANIFEST.txt") `
    -Value $manifest -Encoding utf8

if ($IncludeDockerImages) {
    $baseCompose = Join-Path $repositoryRoot "docker-compose.yml"
    $competitionCompose = Join-Path $repositoryRoot "docker-compose.competition.yml"
    docker compose -f $baseCompose -f $competitionCompose build
    if ($LASTEXITCODE -ne 0) {
        throw "Docker image build failed"
    }
    $imageDirectory = Join-Path $resolvedOutput "offline-images"
    New-Item -ItemType Directory -Path $imageDirectory | Out-Null
    docker save --output (Join-Path $imageDirectory "echo-competition-images.tar") `
        echo-api:competition echo-micro-detector-real:competition
    if ($LASTEXITCODE -ne 0) {
        throw "Docker image export failed"
    }
}

Write-Host "Competition delivery exported to $resolvedOutput"
