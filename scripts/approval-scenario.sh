#!/usr/bin/env bash
# scripts/approval-scenario.sh — the README's approval scenario, end to end.
#
#   docker compose run --rm dev bash scripts/approval-scenario.sh
#
# Creates two API keys (the underwriting service and reviewer "jane"), starts
# `aegis serve` with examples/fintech.yaml in a throwaway directory, runs
# examples/02_approval_flow.py (submit → pause → deny → explain →
# audit export + verify), and stops the server. Exits non-zero if any step
# fails, so CI uses it too.

set -euo pipefail

PORT="${PORT:-8765}"
STATE="$(mktemp -d)"
KEYS="${STATE}/keys.json"
SERVER_PID=""

cleanup() {
  if [[ -n "$SERVER_PID" ]]; then kill "$SERVER_PID" 2>/dev/null || true; wait "$SERVER_PID" 2>/dev/null || true; fi
  rm -rf "$STATE"
}
trap cleanup EXIT

new_key() {  # prints only the aeg-… key from `aegis keys create`
  uv run aegis keys create "$1" --keys-file "$KEYS" | grep -o 'aeg-[0-9a-f]\{64\}'
}

UNDERWRITING_KEY="$(new_key svc-underwriting)"
JANE_KEY="$(new_key jane)"

uv run aegis serve --config examples/fintech.yaml --keys-file "$KEYS" \
  --host 127.0.0.1 --port "$PORT" \
  --ledger-db "${STATE}/ledger.db" --runs-db "${STATE}/runs.db" \
  --checkpoint-db "${STATE}/checkpoints.db" &
SERVER_PID=$!

for _ in $(seq 1 90); do
  curl -sf "http://127.0.0.1:${PORT}/v1/health" > /dev/null && break
  kill -0 "$SERVER_PID" 2>/dev/null || { echo "server exited during startup" >&2; exit 1; }
  sleep 1
done

AEGIS_SERVER_URL="http://127.0.0.1:${PORT}" \
AEGIS_UNDERWRITING_KEY="$UNDERWRITING_KEY" \
AEGIS_JANE_KEY="$JANE_KEY" \
  uv run python examples/02_approval_flow.py
