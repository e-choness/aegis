"""Demo server for scripts/demo.sh --ci.

Starts an Aegis server with:
- FakeProvider on the "default" route
- RegexGuard blocking prompt-injection patterns
- No authentication (--no-auth dev mode)

Usage:
    uv run python scripts/_demo_server.py <port>
"""

from __future__ import annotations

import sys

import uvicorn

from aegis_core.guardrails.regex_guard import RegexGuard
from aegis_core.guardrails.spine import GuardNode
from aegis_core.pipeline.executor import PipelineExecutor
from aegis_core.testing.providers import FakeProvider
from aegis_server.app import create_app

_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 18091

executor = PipelineExecutor()
injection_guard = RegexGuard(
    patterns=["ignore.*previous.*instructions", "reveal.*system.*prompt"],
    reason="Prompt injection detected",
    name="injection",
)
guard_node = GuardNode([injection_guard], name="ingress")
executor.register(
    "default",
    provider=FakeProvider(complete_response="[Aegis] Hello! Your request was governed."),
    ingress=[guard_node],
)
app = create_app(executor, no_auth=True)

uvicorn.run(app, host="127.0.0.1", port=_PORT, log_level="error")
