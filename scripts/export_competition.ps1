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
$headCommit = git -C $repositoryRoot rev-parse HEAD
$requestedCommit = git -C $repositoryRoot rev-parse $Ref
if ($LASTEXITCODE -ne 0 -or $headCommit -ne $requestedCommit) {
    throw "Export ref must match the currently checked out clean worktree"
}
git -C $repositoryRoot lfs fsck
if ($LASTEXITCODE -ne 0) {
    throw "Git LFS verification failed"
}
& (Join-Path $PSScriptRoot "verify_micro_model.ps1")

# Copy only paths tracked by Git from the clean working tree. This copies the
# checked-out LFS objects themselves, excludes ignored secrets/runtime data,
# and avoids `git archive` emitting pointer blobs or stalling in LFS filters.
New-Item -ItemType Directory -Path $resolvedOutput | Out-Null
$trackedPaths = git -C $repositoryRoot ls-files
if ($LASTEXITCODE -ne 0 -or -not $trackedPaths) {
    throw "Failed to enumerate tracked delivery files"
}
foreach ($relativePath in $trackedPaths) {
    $sourcePath = Join-Path $repositoryRoot $relativePath
    if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
        throw "Tracked delivery file is missing from the working tree: $relativePath"
    }
    $destinationPath = Join-Path $resolvedOutput $relativePath
    $destinationParent = Split-Path -Parent $destinationPath
    New-Item -ItemType Directory -Force -Path $destinationParent | Out-Null
    Copy-Item -LiteralPath $sourcePath -Destination $destinationPath
}
& (Join-Path $resolvedOutput "scripts\verify_micro_model.ps1") `
    -ModelRoot (Join-Path $resolvedOutput "models\micro_detector")

$manifest = @(
    "ECHO competition delivery",
    "source_ref=$Ref",
    "source_commit=$headCommit",
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
    $imageArchive = Join-Path $imageDirectory "echo-competition-images.tar"
    docker save --output $imageArchive `
        echo-api:competition echo-micro-detector-real:competition
    if ($LASTEXITCODE -ne 0) {
        throw "Docker image export failed"
    }
    $imageArchiveHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $imageArchive).Hash.ToLowerInvariant()
    Set-Content -LiteralPath (Join-Path $imageDirectory "SHA256SUMS.txt") `
        -Value "$imageArchiveHash  echo-competition-images.tar" -Encoding ascii
    Add-Content -LiteralPath (Join-Path $resolvedOutput "DELIVERY-MANIFEST.txt") `
        -Value "docker_images_sha256=$imageArchiveHash" -Encoding utf8
}

Write-Host "Competition delivery exported to $resolvedOutput"
