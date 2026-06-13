"""Example 02 — Approval flow.

Shows how to submit a run for human-in-the-loop (HITL) review and then
approve or deny it programmatically.

Run::

    uv run python examples/02_approval_flow.py
"""

from __future__ import annotations

import asyncio

import httpx

BASE_URL = "http://127.0.0.1:8000"


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # --- 1. Submit a background run that can be paused for approval ------
        run_payload = {
            "messages": [{"role": "user", "content": "Draft a press release."}],
            "route": "default",
            "approvers": [],
            "background": True,
        }
        r = await client.post("/v1/runs", json=run_payload)
        r.raise_for_status()
        run = r.json()
        run_id: str = run["run_id"]
        print(f"[submitted] run_id={run_id}  status={run['status']}")

        # --- 2. Poll until the run reaches a terminal / paused state ---------
        for _ in range(10):
            await asyncio.sleep(0.2)
            sr = await client.get(f"/v1/runs/{run_id}")
            sr.raise_for_status()
            status = sr.json()["status"]
            if status in {"completed", "allowed", "blocked", "paused", "error"}:
                break

        print(f"[status]   {status}")

        if status == "paused":
            # --- 3. Approve the run ------------------------------------------
            rr = await client.post(
                f"/v1/runs/{run_id}/resume",
                json={"decision": "approved"},
            )
            rr.raise_for_status()
            result = rr.json()
            print(f"[approved] response={result['response']!r}")
        else:
            print("[info] Run completed without requiring approval (no approval node in pipeline).")


if __name__ == "__main__":
    print("NOTE: This example requires `aegis dev` running on http://127.0.0.1:8000")
    print("      Start it with:  uv run aegis dev")
    print()
    asyncio.run(main())
