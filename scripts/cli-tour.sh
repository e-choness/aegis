#!/usr/bin/env bash
# scripts/cli-tour.sh — the session replayed in images/terminal-demo.svg.
#
#   docker compose run --rm dev bash scripts/cli-tour.sh
#
# Starts `aegis serve` with examples/cli-tour.yaml in a throwaway directory and
# runs the same commands as the README's terminal replay: list the policy
# packs, send a credential (blocked), a clean question (answered) and one
# carrying a SIN (paused), deny it as reviewer "jane", explain the run, then
# export and verify the evidence ledger. Exits non-zero if a step fails.

set -euo pipefail

PORT="${PORT:-8799}"
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
step() { printf '\n$ %s\n' "$*"; }

SVC_KEY="$(new_key svc-underwriting)"
JANE_KEY="$(new_key jane)"

uv run aegis serve --config examples/cli-tour.yaml --keys-file "$KEYS" \
  --host 127.0.0.1 --port "$PORT" \
  --ledger-db "${STATE}/ledger.db" --runs-db "${STATE}/runs.db" \
  --checkpoint-db "${STATE}/checkpoints.db" > "${STATE}/server.log" 2>&1 &
SERVER_PID=$!
for _ in $(seq 1 90); do
  curl -sf "http://127.0.0.1:${PORT}/v1/health" > /dev/null && break
  kill -0 "$SERVER_PID" 2>/dev/null || { cat "${STATE}/server.log" >&2; exit 1; }
  sleep 1
done

export AEGIS_SERVER_URL="http://127.0.0.1:${PORT}" AEGIS_API_KEY="$SVC_KEY"

step aegis plugin list --group aegis.packs
uv run aegis plugin list --group aegis.packs

step 'aegis runs create "Why is api_key: 8f14e45fceea167a5a36dedd4bea2543 rejected?" --route default'
uv run aegis runs create "Why is api_key: 8f14e45fceea167a5a36dedd4bea2543 rejected?" --route default \
  | tee "${STATE}/blocked.txt"
grep -q 'status: blocked' "${STATE}/blocked.txt"

step 'aegis runs create "What is our refund policy?" --route underwriting'
uv run aegis runs create "What is our refund policy?" --route underwriting | tee "${STATE}/clean.txt"
grep -q 'status: completed' "${STATE}/clean.txt"

step 'aegis runs create "Applicant SIN 046-454-286, assess risk" --route underwriting --approver jane'
uv run aegis runs create "Applicant SIN 046-454-286, assess risk" --route underwriting --approver jane \
  | tee "${STATE}/paused.txt"
grep -q 'status: paused' "${STATE}/paused.txt"
RUN_ID="$(grep -o 'run_id: [0-9a-f-]*' "${STATE}/paused.txt" | cut -d' ' -f2)"

step "AEGIS_API_KEY=\$JANE_KEY aegis runs deny ${RUN_ID}"
AEGIS_API_KEY="$JANE_KEY" uv run aegis runs deny "$RUN_ID"

step "aegis explain ${RUN_ID}"
uv run aegis explain "$RUN_ID"

step 'aegis audit export -o ledger.jsonl && aegis audit verify ledger.jsonl'
uv run aegis audit export -o "${STATE}/ledger.jsonl"
uv run aegis audit verify "${STATE}/ledger.jsonl"
