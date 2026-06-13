"""Scenario 05 — Data residency enforcement.

Demonstrates:
- How aegis-pack-residency labels requests with their classification.
- Fail-closed routing: requests classified as EU-restricted are never
  sent to a provider whose declared region does not match.
- Lint validation: `aegis policy lint` flags a declared-vs-endpoint
  region mismatch before runtime.

Prerequisites:
    - aegis-pack-classification and aegis-pack-residency installed.
    - A config with at least one EU-only route and one US route.
    - Set AEGIS_SERVER_URL and AEGIS_API_KEY as appropriate.

Note:
    This scenario shows the event log labels added by the classification
    and residency packs. Run `aegis policy lint examples/aegis.yaml`
    to see lint validation of provider region declarations.
"""

from __future__ import annotations

import os
import subprocess
import sys

from aegis_sdk import AegisClient

SERVER_URL = os.environ.get("AEGIS_SERVER_URL", "http://localhost:8000")
API_KEY = os.environ.get("AEGIS_API_KEY", "")
EU_ROUTE = os.environ.get("AEGIS_EU_ROUTE", "eu")
US_ROUTE = os.environ.get("AEGIS_US_ROUTE", "default")


def main() -> None:
    with AegisClient(base_url=SERVER_URL, api_key=API_KEY) as client:
        print("── Scenario 05: Data Residency ─────────────────────")

        # Show lint output for the example config.
        print("\n[1] Policy lint (residency declarations):")
        result = subprocess.run(
            [sys.executable, "-m", "aegis_cli", "policy", "lint", "examples/aegis.yaml"],
            capture_output=True,
            text=True,
        )
        lint_out = result.stdout.strip() or "(no issues found)"
        for line in lint_out.splitlines()[:10]:
            print(f"  {line}")

        # Send a request on the US route and check labels.
        print(f"\n[2] Request on US route ({US_ROUTE!r}):")
        run = client.create_run(
            [{"role": "user", "content": "Summarise the Q3 sales report."}],
            route=US_ROUTE,
        )
        print(f"  status : {run.status}")
        labels = {}
        for evt in run.events:
            if evt.get("data", {}).get("labels"):
                labels.update(evt["data"]["labels"])
        print(f"  labels : {labels or '(none — classification pack not active on this route)'}")

        # Attempt on the EU route (may fail-closed if not configured).
        print(f"\n[3] Request on EU route ({EU_ROUTE!r}):")
        try:
            eu_run = client.create_run(
                [{"role": "user", "content": "Summarise the Q3 sales report."}],
                route=EU_ROUTE,
            )
            print(f"  status : {eu_run.status}")
        except Exception as exc:
            print(f"  error  : {exc} (route may not be configured; this is expected)")


if __name__ == "__main__":
    main()
