#!/bin/bash
# Fix container startup by ensuring packages are properly installed

set -e

echo "===== Container Startup Fix ====="
echo "Current working directory: $(pwd)"
echo ""

# Ensure we're in /app
cd /app

# Step 1: Verify workspace structure
echo "1. Verifying workspace structure..."
if [ ! -f "pyproject.toml" ]; then
  echo "ERROR: No pyproject.toml in /app"
  exit 1
fi
echo "   ✓ pyproject.toml exists"

# Step 2: Remove stale venv if it exists (fresh sync is safer)
if [ -d ".venv" ]; then
  echo "2. Clearing stale virtual environment..."
  rm -rf .venv
fi

# Step 3: Fresh sync with all packages
echo "3. Running uv sync with all packages..."
uv sync --all-packages --python 3.12 --refresh || {
  echo "ERROR: uv sync failed"
  exit 1
}
echo "   ✓ uv sync completed"

# Step 4: Verify packages are installed
echo "4. Verifying package installations..."
uv pip show aegis-gateway-cli | grep -q "^Name:" && echo "   ✓ aegis-gateway-cli installed" || echo "   ✗ aegis-gateway-cli NOT installed"
uv pip show aegis-gateway-core | grep -q "^Name:" && echo "   ✓ aegis-gateway-core installed" || echo "   ✗ aegis-gateway-core NOT installed"
uv pip show aegis-gateway-server | grep -q "^Name:" && echo "   ✓ aegis-gateway-server installed" || echo "   ✗ aegis-gateway-server NOT installed"

# Step 5: Verify entry point
echo "5. Testing entry point..."
if /app/.venv/bin/aegis --help > /dev/null 2>&1; then
  echo "   ✓ Entry point works"
else
  echo "   ✗ Entry point failed"
  echo "   Attempting to reinstall packages in editable mode..."
  cd /app/packages/aegis-cli && uv pip install -e . && cd /app
  cd /app/packages/aegis-core && uv pip install -e . && cd /app
  cd /app/packages/aegis-server && uv pip install -e . && cd /app
  echo "   Retesting entry point..."
  /app/.venv/bin/aegis --help > /dev/null 2>&1 || {
    echo "   ERROR: Entry point still failed after reinstall"
    exit 1
  }
  echo "   ✓ Entry point works after reinstall"
fi

echo ""
echo "===== Container Ready ====="
echo "Starting aegis server..."
echo ""

# Run the actual server
exec uv run aegis dev --host 0.0.0.0 --port 7860
