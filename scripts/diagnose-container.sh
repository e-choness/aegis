#!/bin/bash
# Diagnose container startup issues for aegis-server on HF Spaces

set -e

echo "===== Container Diagnostic Report ====="
echo "Date: $(date)"
echo ""

echo "1. Python environment:"
which python
python --version
echo ""

echo "2. Virtual environment:"
echo "VIRTUAL_ENV=$VIRTUAL_ENV"
echo "PYTHONPATH=$PYTHONPATH"
ls -la /app/.venv/bin/ | grep aegis || echo "  (no aegis entry point found)"
echo ""

echo "3. Installed packages (uv pip list):"
uv pip list 2>/dev/null | grep -i aegis || echo "  (no aegis packages found)"
echo ""

echo "4. Workspace structure:"
echo "  pyproject.toml members:"
grep -A 10 'tool.uv.workspace' /app/pyproject.toml || echo "  (no workspace config)"
echo ""

echo "5. Checking if packages can be imported directly:"
python -c "import sys; print('Python path:'); print('\\n'.join(sys.path))"
echo ""
python -c "try:
    import aegis_cli
    print('✓ aegis_cli importable')
except ImportError as e:
    print(f'✗ aegis_cli NOT importable: {e}')" 2>&1 || true
echo ""

echo "6. Trying to run aegis entry point:"
/app/.venv/bin/aegis --help 2>&1 || echo "  (entry point failed)"
echo ""

echo "===== End Diagnostic ====="
