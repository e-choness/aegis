"""Scenario 02 — Vendor-diligence approval flow (Phase 4).

The scenario the README hero cast is built from: a loan-underwriting
request carrying a Canadian SIN gets routed to a US-region model. The
`residency_ca` guardrail doesn't block that outright — it's
`require_approval`, not fail-closed — so the run pauses for a named human
reviewer instead. The reviewer denies it. The evidence ledger records both
the pause and the denial, with the reviewer's identity attached, and the
whole chain verifies offline.

Demonstrates:
- Submitting a request that trips a `require_approval` residency guardrail.
- Listing pending runs and denying one as a named principal (not "anonymous").
- `aegis explain` rendering the verdict trail with the approver attached.
- `aegis audit export` + `aegis audit verify` on just that route.

One command does all of the setup below and runs this script:

    docker compose run --rm dev bash scripts/approval-scenario.sh

Manual prerequisites:
    aegis keys create svc-underwriting --keys-file examples/fintech-keys.json
    aegis keys create jane             --keys-file examples/fintech-keys.json
    aegis serve --config examples/fintech.yaml \\
        --keys-file examples/fintech-keys.json \\
        --ledger-db /tmp/fintech-ledger.db \\
        --checkpoint-db /tmp/fintech-checkpoints.db

    Then set AEGIS_UNDERWRITING_KEY and AEGIS_JANE_KEY to the two printed keys.

Note:
    The route's PII guardrail loads a spaCy model on its first real request
    (Presidio's `AnalyzerEngine`) — the first call to `create_run()` below
    can take ~20-30s. Subsequent calls are fast. If recording a timed demo
    cast, send one throwaway request first so that cost doesn't show on camera.
"""

from __future__ import annotations

import os
import subprocess
import sys

from aegis_sdk import AegisClient

SERVER_URL = os.environ.get("AEGIS_SERVER_URL", "http://localhost:8000")
UNDERWRITING_KEY = os.environ.get("AEGIS_UNDERWRITING_KEY", "")
JANE_KEY = os.environ.get("AEGIS_JANE_KEY", "")
ROUTE = os.environ.get("AEGIS_ROUTE", "underwriting")


def _run_aegis_cli(*args: str, api_key: str) -> str:
    """Invoke the real `aegis` CLI as a subprocess so this script's output
    matches exactly what a terminal (and the asciinema cast) would show.
    """
    env = {**os.environ, "AEGIS_SERVER_URL": SERVER_URL, "AEGIS_API_KEY": api_key}
    result = subprocess.run(
        ["aegis", *args],
        env=env,
        capture_output=True,
        text=True,
    )
    print(result.stdout, end="")
    if result.returncode != 0:
        print(result.stderr, end="", file=sys.stderr)
        raise SystemExit(f"`aegis {' '.join(args)}` failed (exit {result.returncode})")
    return result.stdout


def main() -> None:
    if not UNDERWRITING_KEY or not JANE_KEY:
        print("Set AEGIS_UNDERWRITING_KEY and AEGIS_JANE_KEY first — see this file's docstring.")
        raise SystemExit(1)

    print("── Scenario 02: Vendor-Diligence Approval Flow ─────────────")

    print("\n[1] Submitting an underwriting request containing a SIN, to a US-region model:")
    with AegisClient(base_url=SERVER_URL, api_key=UNDERWRITING_KEY) as client:
        run = client.create_run(
            [
                {
                    "role": "user",
                    "content": "Applicant SIN is 046-454-286, please assess underwriting risk.",
                }
            ],
            route=ROUTE,
            approvers=["jane"],
        )
    print(f"  run_id : {run.run_id}")
    print(f"  status : {run.status}")

    if run.status != "paused":
        print(f"\n  Expected 'paused' (require_approval residency guard); got {run.status!r}.")
        print("  Is the server running examples/fintech.yaml?")
        raise SystemExit(1)

    print("\n[2] Pending runs:")
    _run_aegis_cli("runs", "list", "--pending", api_key=JANE_KEY)

    print("\n[3] jane denies it:")
    _run_aegis_cli("runs", "deny", run.run_id, api_key=JANE_KEY)

    print("\n[4] The full verdict trail, with the approver attached:")
    _run_aegis_cli("explain", run.run_id, api_key=JANE_KEY)

    print(f"\n[5] Export the evidence for route={ROUTE!r} and verify the chain offline:")
    export_path = "/tmp/fintech-evidence.jsonl"
    _run_aegis_cli("audit", "export", "--route", ROUTE, "--output", export_path, api_key=JANE_KEY)
    _run_aegis_cli("audit", "verify", export_path, api_key=JANE_KEY)


if __name__ == "__main__":
    main()
