#!/bin/bash
# Sync aegis-server repo from main aegis repo to HF Spaces local clone
# Usage: ./scripts/sync-to-hf-spaces.sh <path-to-hf-spaces-clone>

set -e

MAIN_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HF_SPACES_REPO="${1:-./../aegis-server}"

# Normalize paths
HF_SPACES_REPO="$(cd "$HF_SPACES_REPO" 2>/dev/null && pwd)" || {
  echo "ERROR: HF Spaces repo not found at $HF_SPACES_REPO"
  echo "Usage: ./scripts/sync-to-hf-spaces.sh <path-to-hf-spaces-clone>"
  exit 1
}

echo "===== Syncing to HF Spaces ====="
echo "Source (main):     $MAIN_REPO"
echo "Target (HF):       $HF_SPACES_REPO"
echo ""

# Verify both are git repos
[ -d "$MAIN_REPO/.git" ] || {
  echo "ERROR: Main repo is not a git repository"
  exit 1
}
[ -d "$HF_SPACES_REPO/.git" ] || {
  echo "ERROR: HF Spaces repo is not a git repository"
  exit 1
}

echo "1. Copying Python workspace files..."
# Copy all Python workspace files
rsync -av --delete \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.pytest_cache' \
  --exclude 'dist' \
  --exclude 'build' \
  --exclude '.eggs' \
  --exclude '*.egg-info' \
  --exclude '.mypy_cache' \
  --exclude 'node_modules' \
  --exclude '.npm' \
  "$MAIN_REPO/pyproject.toml" \
  "$MAIN_REPO/uv.lock" \
  "$MAIN_REPO/ruff.toml" \
  "$MAIN_REPO/pyrightconfig.json" \
  "$MAIN_REPO/packages/" \
  "$MAIN_REPO/sdk/python/" \
  "$HF_SPACES_REPO/" \
  2>&1 | grep -E '(created|deleted|file list)' || true

echo "   ✓ Python workspace synced"
echo ""

echo "2. Copying container and script files..."
rsync -av \
  "$MAIN_REPO/Dockerfile" \
  "$MAIN_REPO/scripts/diagnose-container.sh" \
  "$MAIN_REPO/scripts/fix-container-entrypoint.sh" \
  "$HF_SPACES_REPO/" 2>&1 | grep -E '(Dockerfile|\.sh)' || true

echo "   ✓ Container files synced"
echo ""

echo "3. Checking for other key files..."
for file in .gitignore README.md; do
  if [ -f "$MAIN_REPO/$file" ]; then
    cp "$MAIN_REPO/$file" "$HF_SPACES_REPO/"
    echo "   ✓ Copied $file"
  fi
done

echo ""
echo "4. Verifying sync..."
cd "$HF_SPACES_REPO"
if [ -f "pyproject.toml" ] && [ -f "Dockerfile" ] && [ -f "scripts/fix-container-entrypoint.sh" ]; then
  echo "   ✓ All required files present"
else
  echo "   ✗ Some files are missing"
  echo "     - pyproject.toml: $([ -f 'pyproject.toml' ] && echo '✓' || echo '✗')"
  echo "     - Dockerfile: $([ -f 'Dockerfile' ] && echo '✓' || echo '✗')"
  echo "     - scripts/fix-container-entrypoint.sh: $([ -f 'scripts/fix-container-entrypoint.sh' ] && echo '✓' || echo '✗')"
  exit 1
fi

echo ""
echo "===== Sync Complete ====="
echo "Next steps:"
echo "  1. cd $HF_SPACES_REPO"
echo "  2. git add -A"
echo "  3. git commit -m 'sync: update from main aegis repo'"
echo "  4. git push"
