# Sync aegis-server repo from main aegis repo to HF Spaces local clone
# Usage: .\scripts\sync-to-hf-spaces.ps1 -HFSpacesPath <path-to-hf-spaces-clone>

param(
    [Parameter(Mandatory=$false)]
    [string]$HFSpacesPath = "../aegis-server"
)

$ErrorActionPreference = "Stop"

$MainRepo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$HFSpacesRepo = Resolve-Path -LiteralPath $HFSpacesPath -ErrorAction Stop

Write-Host "===== Syncing to HF Spaces =====" -ForegroundColor Cyan
Write-Host "Source (main):     $MainRepo"
Write-Host "Target (HF):       $HFSpacesRepo"
Write-Host ""

# Verify both are git repos
if (-not (Test-Path "$MainRepo\.git")) {
    Write-Host "ERROR: Main repo is not a git repository" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path "$HFSpacesRepo\.git")) {
    Write-Host "ERROR: HF Spaces repo is not a git repository" -ForegroundColor Red
    exit 1
}

Write-Host "1. Copying Python workspace files..." -ForegroundColor Yellow

# Copy workspace root files
@("pyproject.toml", "uv.lock", "ruff.toml", "pyrightconfig.json") | ForEach-Object {
    $src = Join-Path $MainRepo $_
    $dst = Join-Path $HFSpacesRepo $_
    if (Test-Path $src) {
        Copy-Item $src $dst -Force
        Write-Host "   ✓ Copied $_"
    }
}

# Copy directories (packages, sdk/python)
@("packages", "sdk") | ForEach-Object {
    $src = Join-Path $MainRepo $_
    $dst = Join-Path $HFSpacesRepo $_
    if (Test-Path $src) {
        # Remove old directory
        if (Test-Path $dst) {
            Remove-Item $dst -Recurse -Force
        }
        # Copy new directory
        Copy-Item $src $dst -Recurse -Force
        Write-Host "   ✓ Copied $_ directory"
    }
}

Write-Host "   ✓ Python workspace synced" -ForegroundColor Green
Write-Host ""

Write-Host "2. Copying container and script files..." -ForegroundColor Yellow
@("Dockerfile", "scripts/diagnose-container.sh", "scripts/fix-container-entrypoint.sh") | ForEach-Object {
    $src = Join-Path $MainRepo $_
    $dst = Join-Path $HFSpacesRepo $_
    if (Test-Path $src) {
        $dstDir = Split-Path -Parent $dst
        if (-not (Test-Path $dstDir)) {
            New-Item $dstDir -ItemType Directory -Force | Out-Null
        }
        Copy-Item $src $dst -Force
        Write-Host "   ✓ Copied $_"
    }
}
Write-Host "   ✓ Container files synced" -ForegroundColor Green
Write-Host ""

Write-Host "3. Checking for other key files..." -ForegroundColor Yellow
@(".gitignore", "README.md") | ForEach-Object {
    $src = Join-Path $MainRepo $_
    $dst = Join-Path $HFSpacesRepo $_
    if (Test-Path $src) {
        Copy-Item $src $dst -Force
        Write-Host "   ✓ Copied $_"
    }
}

Write-Host ""
Write-Host "4. Verifying sync..." -ForegroundColor Yellow
Push-Location $HFSpacesRepo
try {
    $filesOk = (Test-Path "pyproject.toml") -and (Test-Path "Dockerfile") -and (Test-Path "scripts/fix-container-entrypoint.sh")
    if ($filesOk) {
        Write-Host "   ✓ All required files present" -ForegroundColor Green
    } else {
        Write-Host "   ✗ Some files are missing" -ForegroundColor Red
        Write-Host "     - pyproject.toml: $((Test-Path 'pyproject.toml') ? '✓' : '✗')"
        Write-Host "     - Dockerfile: $((Test-Path 'Dockerfile') ? '✓' : '✗')"
        Write-Host "     - scripts/fix-container-entrypoint.sh: $((Test-Path 'scripts/fix-container-entrypoint.sh') ? '✓' : '✗')"
        exit 1
    }
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "===== Sync Complete =====" -ForegroundColor Green
Write-Host "Next steps:"
Write-Host "  1. cd $HFSpacesRepo"
Write-Host "  2. git add -A"
Write-Host "  3. git commit -m 'sync: update from main aegis repo'"
Write-Host "  4. git push"
