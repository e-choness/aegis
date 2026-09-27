"""Import every module of every installed Aegis package, then serve a request.

Run by the release workflow against the freshly built wheels, installed in a
clean environment, so a file that was never committed (and so isn't in the
wheel) fails the release instead of the users who install it. A missing
third-party module is fine — optional extras aren't installed — but a
missing Aegis module is not.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys

PACKAGES = [
    "aegis_core",
    "aegis_server",
    "aegis_cli",
    "aegis_sdk",
    "aegis_pack_pii",
    "aegis_pack_classification",
    "aegis_pack_residency",
    "aegis_pack_budgets",
    "aegis_pack_content",
]


def import_everything() -> list[str]:
    failures = []
    for name in PACKAGES:
        package = importlib.import_module(name)
        for info in pkgutil.walk_packages(package.__path__, prefix=f"{name}."):
            try:
                importlib.import_module(info.name)
            except ModuleNotFoundError as exc:
                if (exc.name or "").startswith("aegis"):
                    failures.append(f"{info.name}: {exc}")
            except ImportError as exc:  # e.g. a name missing from one of our modules
                failures.append(f"{info.name}: {exc}")
    return failures


def serve_a_request() -> None:
    from starlette.testclient import TestClient

    from aegis_core.pipeline.executor import PipelineExecutor
    from aegis_core.testing.providers import FakeProvider
    from aegis_server.app import create_app

    executor = PipelineExecutor()
    executor.register("default", provider=FakeProvider(complete_response="ok"))
    with TestClient(create_app(executor, no_auth=True)) as client:
        assert client.get("/v1/health").status_code == 200
        assert "Pipeline Showcase" in client.get("/showcase").text  # the page ships in the wheel
        reply = client.post(
            "/v1/chat/completions",
            json={"model": "default", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert reply.status_code == 200, reply.text


if __name__ == "__main__":
    problems = import_everything()
    for problem in problems:
        print(f"FAIL {problem}", file=sys.stderr)
    if problems:
        sys.exit(1)
    serve_a_request()
    print(f"ok: every module of {len(PACKAGES)} packages imports, and the server answers")
