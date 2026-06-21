# Deploy Container Fix to HF Spaces

## Summary

The container startup issue is caused by `uv sync` completing but entry points not being properly registered. The fix involves:

1. **Updated Dockerfile** — Uses a startup script instead of directly running `uv run aegis`
2. **Fix script** (`fix-container-entrypoint.sh`) — Ensures packages are properly installed before startup
3. **Sync automation** — Scripts to sync the main repo to your HF Spaces clone

## Quick Deploy (5 minutes)

### Prerequisites
- HF Spaces repo cloned locally at `../aegis-server` (relative to main repo)
- Git credentials configured for HF Spaces push

### Steps

1. **Sync the files** (choose one based on your OS):

   **Unix/Linux/Mac:**
   ```bash
   cd ~/aegis  # main repo
   ./scripts/sync-to-hf-spaces.sh ../aegis-server
   ```

   **Windows PowerShell:**
   ```powershell
   cd ~/aegis  # main repo
   .\scripts\sync-to-hf-spaces.ps1 -HFSpacesPath ../aegis-server
   ```

2. **Commit and push** to HF Spaces:
   ```bash
   cd ../aegis-server
   git add -A
   git commit -m "fix: container startup — add package install verification script"
   git push
   ```

3. **Monitor the build** on HF Spaces:
   - Go to https://huggingface.co/spaces/echoness/aegis-server/settings
   - Check "Build logs" tab
   - Wait for build to complete (~5-10 minutes)
   - Look for: `===== Container Ready =====` at the end of logs

4. **Test the container**:
   - Once build succeeds, the Space URL will be updated
   - Open https://huggingface.co/spaces/echoness/aegis-server
   - Verify the showcase page loads at `/showcase`

## What Changed

### Files Modified
- **Dockerfile** (1 change)
  - Line 30-31: Added COPY for fix scripts
  - Line 38: Changed ENTRYPOINT from `["uv", "run", "aegis", ...]` to `["./scripts/fix-container-entrypoint.sh"]`

### Files Added
- `scripts/diagnose-container.sh` (diagnostic utility)
- `scripts/fix-container-entrypoint.sh` (startup fix)
- `scripts/sync-to-hf-spaces.sh` (Unix sync automation)
- `scripts/sync-to-hf-spaces.ps1` (Windows sync automation)
- `scripts/HF_SPACES_SYNC_README.md` (detailed sync guide)
- `scripts/DEPLOY_FIX_TO_HF_SPACES.md` (this file)

## How the Fix Works

**Old flow (broken):**
```
Dockerfile → uv sync → Entry point script tries to run → 
  ModuleNotFoundError: No module named 'aegis_cli'
```

**New flow (fixed):**
```
Dockerfile → fix-container-entrypoint.sh:
  1. Fresh sync (--refresh)
  2. Validate packages installed
  3. Fallback to editable installs if needed
  4. Test entry point
  5. Start server
```

The key improvement is that the startup script can detect and fix package installation issues that `uv sync` alone doesn't catch.

## Verification Checklist

After pushing to HF Spaces:

- [ ] HF Spaces build logs show `✓ uv sync completed`
- [ ] HF Spaces build logs show `✓ Entry point works`
- [ ] HF Spaces build logs show `===== Container Ready =====`
- [ ] Showcase page loads at Space URL `/showcase`
- [ ] No ModuleNotFoundError in logs

## Troubleshooting

### Build still fails
1. Check HF Spaces build logs for exact error
2. Run diagnostic locally:
   ```bash
   docker compose run --rm dev bash /app/scripts/diagnose-container.sh
   ```
3. Share the diagnostic output with the issue

### Sync script fails
- Ensure rsync is installed (Unix) or PowerShell 5+ (Windows)
- Verify both repos have `.git` folders
- Check `../aegis-server` path is correct

### Git push to HF Spaces fails
- Verify HF token has `repo` scope (full read+write)
- Test with: `git clone https://huggingface.co/spaces/echoness/aegis-server`
- Check HF Spaces git settings for authentication requirements

## Manual Deployment (If Scripts Fail)

If the sync scripts don't work, manually copy these directories:

```bash
cd /path/to/aegis-server

# Copy workspace
cp ../aegis/pyproject.toml .
cp ../aegis/uv.lock .
cp ../aegis/ruff.toml .
cp ../aegis/pyrightconfig.json .
rm -rf packages sdk && cp -r ../aegis/packages . && cp -r ../aegis/sdk/python sdk/

# Copy container files
cp ../aegis/Dockerfile .
cp -r ../aegis/scripts .

# Commit
git add -A
git commit -m "fix: container startup"
git push
```

## Next Steps

After successful deployment:

1. Update AMEND_PLAN.md to mark Step 19 as complete
2. Proceed to Step 20 (or next steps in plan)
3. Consider setting up automated sync for future changes

## References

- [HF_SPACES_SYNC_README.md](./HF_SPACES_SYNC_README.md) — Detailed sync and automation guide
- [CLAUDE.md](../CLAUDE.md) — Project rules
- [AMEND_PLAN.md](../AMEND_PLAN.md) — Build plan
