"""Scenario 03 — Governed MCP tool call.

Demonstrates:
- Sending a request that triggers a tool call through an MCP-enabled route.
- The event log shows: ingress scan → tool-call scan → tool execution →
  tool-result scan → egress scan.
- An exfiltration attempt (masked PII in tool args) is blocked before
  the tool is invoked.

Prerequisites:
    - Aegis server running with an MCP-enabled route.
    - Set AEGIS_SERVER_URL and AEGIS_API_KEY as appropriate.
    - Set AEGIS_MCP_ROUTE (default: "mcp") to the configured route name.

Note:
    This scenario illustrates the event log structure produced by a
    governed MCP tool call. Configure a route with mcp.servers pointing
    at a local MCP server and set the route name via AEGIS_MCP_ROUTE.
"""

from __future__ import annotations

import os

from aegis_sdk import AegisClient

SERVER_URL = os.environ.get("AEGIS_SERVER_URL", "http://localhost:8000")
API_KEY = os.environ.get("AEGIS_API_KEY", "")
MCP_ROUTE = os.environ.get("AEGIS_MCP_ROUTE", "mcp")


def main() -> None:
    with AegisClient(base_url=SERVER_URL, api_key=API_KEY) as client:
        print("── Scenario 03: Governed MCP Tool Call ─────────────")

        print(f"\n[1] Sending request on route '{MCP_ROUTE}':")
        run = client.create_run(
            [{"role": "user", "content": "What files are in the current directory?"}],
            route=MCP_ROUTE,
        )
        print(f"  status   : {run.status}")
        print(f"  response : {(run.response or '')[:120]}")

        print("\n[2] Event log:")
        stages_seen: list[str] = []
        for evt in run.events:
            stage = evt.get("stage", "?")
            node = evt.get("node", "?")
            etype = evt.get("event_type", "?")
            data = evt.get("data", {})
            if stage not in stages_seen:
                stages_seen.append(stage)
                print(f"\n  [{stage}]")
            verdict = data.get("verdict", "")
            reason = data.get("reason", "")
            suffix = f"  verdict={verdict} reason={reason!r}" if verdict else ""
            print(f"    {node}:{etype}{suffix}")


if __name__ == "__main__":
    main()
