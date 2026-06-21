# HF Spaces Sync & Container Fix Guide

## The Problem

The container on HF Spaces fails to start with:
```
ModuleNotFoundError: No module named 'aegis_cli'
```

This happens because:
1. `uv sync` completes successfully
2. The packages are built, but the entry point script (`aegis`) can't find the `aegis_cli` module
3. This is typically caused by missing editable installs or stale cache in the virtual environment

## The Solution

### 1. Updated Dockerfile
The main `Dockerfile` now uses a startup script (`fix-container-entrypoint.sh`) instead of running `uv run aegis` directly. This script:
- Ensures a fresh virtual environment
- Runs `uv sync` with a refresh flag
- Validates that all packages are installed
- Falls back to editable installs if needed
- Then starts the server

### 2. Sync Scripts
Two scripts automate syncing from the main aegis repo to your HF Spaces clone:

#### On Unix/Linux/Mac:
```bash
./scripts/sync-to-hf-spaces.sh ../aegis-server
```

#### On Windows (PowerShell):
```powershell
.\scripts\sync-to-hf-spaces.ps1 -HFSpacesPath ../aegis-server
```

### 3. Diagnostic Script
If you need to debug container issues:
```bash
# Inside the container
bash /app/scripts/diagnose-container.sh
```

This reports:
- Python version and environment
- Installed packages
- Module import status
- Entry point functionality

## Setup Instructions

### First Time Setup

1. **Clone the HF Spaces repo locally** (if you haven't already):
   ```bash
   git clone https://huggingface.co/spaces/echoness/aegis-server ~/aegis-server
   cd ~/aegis-server
   ```

2. **Sync from main repo**:
   ```bash
   cd ~/aegis  # main repo
   ./scripts/sync-to-hf-spaces.sh ../aegis-server
   ```

3. **Commit and push**:
   ```bash
   cd ~/aegis-server
   git add -A
   git commit -m "sync: update from main aegis repo (fix container startup)"
   git push
   ```

4. **Trigger a rebuild** on HF Spaces:
   - The space will auto-build on git push
   - Check the build logs in HF Spaces settings
   - The container should now start successfully

### Ongoing Sync

Whenever you make changes to the aegis repo and want to sync to HF Spaces:

```bash
cd ~/aegis
./scripts/sync-to-hf-spaces.sh ../aegis-server
cd ../aegis-server
git add -A
git commit -m "sync: <describe changes>"
git push
```

## What Gets Synced

The sync scripts copy:
- **Root files**: `pyproject.toml`, `uv.lock`, `ruff.toml`, `pyrightconfig.json`
- **Directories**: `packages/`, `sdk/python/`, `scripts/`
- **Container**: `Dockerfile`
- **Utilities**: `.gitignore`, `README.md`

They exclude:
- `.git` and git metadata
- Virtual environments (`.venv`, `venv`)
- Build artifacts (`dist/`, `build/`, `*.egg-info`)
- Cache files (`__pycache__`, `.pytest_cache`, `.mypy_cache`)

## Troubleshooting

### Container still fails to start

1. Check the HF Spaces build logs for the exact error
2. Run the diagnostic script locally in Docker:
   ```bash
   docker compose run --rm dev bash /app/scripts/diagnose-container.sh
   ```
3. Look for:
   - Missing packages in `uv pip list`
   - Import errors when testing `aegis_cli`
   - Entry point not found

### Sync script fails

**On Unix:**
- Ensure you have `rsync` installed: `brew install rsync` (Mac) or `apt-get install rsync` (Linux)
- Ensure both repos are git repositories with valid `.git` folders

**On Windows:**
- Make sure you're running PowerShell (not cmd)
- The script uses PowerShell's built-in `Copy-Item` which handles Windows paths

### Git push fails to HF Spaces

- Verify your HF token has `repo` scope (write access)
- Check that you're using the correct HF Spaces git URL
- Ensure `git` can authenticate (try `git push` on a test branch)

## Automation (Optional)

You can set up git hooks to auto-sync:

**`.git/hooks/post-commit`** (in main repo):
```bash
#!/bin/bash
if grep -q "packages/\|pyproject.toml\|Dockerfile\|uv.lock" <(git diff-tree --no-commit-id --name-only -r HEAD~1 HEAD); then
  echo "📦 Files changed that affect HF Spaces — sync?"
  echo "Run: ./scripts/sync-to-hf-spaces.sh ../aegis-server"
fi
```

Or set up a scheduled job:
```bash
# Check every 30 minutes if sync is needed
*/30 * * * * cd ~/aegis && ./scripts/sync-to-hf-spaces.sh ../aegis-server 2>&1 | grep -q "ERROR" && exit 1 || git -C ../aegis-server push 2>/dev/null
```

## Files Changed

- `Dockerfile` — Updated entrypoint to use fix script
- `scripts/diagnose-container.sh` — New diagnostic utility
- `scripts/fix-container-entrypoint.sh` — New container startup fix
- `scripts/sync-to-hf-spaces.sh` — New Unix/Linux/Mac sync script
- `scripts/sync-to-hf-spaces.ps1` — New Windows PowerShell sync script
- `scripts/HF_SPACES_SYNC_README.md` — This file

## References

- [CLAUDE.md](../CLAUDE.md) — Project rules
- [AMEND_PLAN.md](../AMEND_PLAN.md) — Build steps
- [HF Spaces Git Workflow Memory](../../.openclaude/projects/D--projects-aegis/memory/team/hf-spaces-git-workflow.md)
