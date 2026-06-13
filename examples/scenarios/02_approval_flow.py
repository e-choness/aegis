"""Scenario 02 — Human-in-the-loop approval flow.

Demonstrates:
- Submitting a run that requires human approval (background=True + approvers).
- Polling the run status until it is paused.
- Approving the run via the resume endpoint.
- Verifying the run completes after approval.

Prerequisites:
    - Aegis server running with a checkpointer-enabled route that uses
      require_approval (e.g. aegis dev with an approval-gated config).
    - Set AEGIS_SERVER_URL and AEGIS_API_KEY as appropriate.

Note:
    The default dev server route does not require approval.
    This scenario illustrates the SDK call pattern used with a
    properly configured approval-gated route.
"""

from __future__ import annotations

import os
import time

from aegis_sdk import AegisClient

SERVER_URL = os.environ.get("AEGIS_SERVER_URL", "http://localhost:8000")
API_KEY = os.environ.get("AEGIS_API_KEY", "")
APPROVER = os.environ.get("AEGIS_APPROVER", "")


def main() -> None:
    with AegisClient(base_url=SERVER_URL, api_key=API_KEY) as client:
        print("── Scenario 02: Approval Flow ──────────────────────")

        # Submit a background run that requires approval.
        print("\n[1] Submitting run (background, requires approval):")
        run = client.create_run(
            [{"role": "user", "content": "Draft a contract clause for data retention."}],
            route="default",
            background=True,
            approvers=[APPROVER] if APPROVER else [],
        )
        run_id = run.run_id
        print(f"  run_id : {run_id}")
        print(f"  status : {run.status}")

        # Poll until paused (or completed if approval is not required on this route).
        print("\n[2] Polling for paused status …")
        for _ in range(10):
            status_resp = client.get_run(run_id)
            print(f"  status : {status_resp.status}")
            if status_resp.status in ("paused", "completed", "blocked", "denied", "error"):
                break
            time.sleep(1)

        if status_resp.status != "paused":
            print(f"\n  Route not configured for approval (status={status_resp.status}).")
            print("  Point this scenario at an approval-gated route to see the full flow.")
            return

        # Approve the run.
        print("\n[3] Approving run …")
        resume = client.resume_run(run_id, "approved")
        print(f"  status   : {resume.status}")
        print(f"  response : {resume.response}")


if __name__ == "__main__":
    main()
