"""Tests for GET /v1/health (Phase 0)."""

from __future__ import annotations

from starlette.testclient import TestClient


def test_health_ok(client_no_auth: TestClient) -> None:
    resp = client_no_auth.get("/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"


def test_health_no_digest_when_not_set(client_no_auth: TestClient) -> None:
    resp = client_no_auth.get("/v1/health")
    body = resp.json()
    assert body["config_digest"] is None
    assert body["config_path"] is None


def test_health_returns_digest(client_with_digest: TestClient) -> None:
    resp = client_with_digest.get("/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["config_digest"] == "sha256:abc123"
    assert body["config_path"] == "/etc/aegis/aegis.yaml"


def test_health_unauthenticated_allowed(client_with_digest: TestClient) -> None:
    """Health endpoint must be reachable without auth headers."""
    resp = client_with_digest.get("/v1/health")
    assert resp.status_code == 200


class _Warm:
    name = "warm"

    def __init__(self, fail: bool = False) -> None:
        self.calls = 0
        self._fail = fail

    def warmup(self) -> None:
        self.calls += 1
        if self._fail:
            raise RuntimeError("model missing")

    async def run(self, state: object) -> object:
        from aegis_core.pipeline.state import RunStateDelta

        return RunStateDelta()


def _app_with(node: _Warm):  # type: ignore[no-untyped-def]
    from aegis_core.pipeline.executor import PipelineExecutor
    from aegis_core.testing.providers import FakeProvider
    from aegis_server.app import create_app

    executor = PipelineExecutor()
    executor.register("default", provider=FakeProvider(), ingress=[node])  # type: ignore[list-item]
    return create_app(executor, no_auth=True)


def _wait_for(client: TestClient, predicate) -> dict:  # type: ignore[no-untyped-def,type-arg]
    import time

    body: dict = {}  # type: ignore[type-arg]
    for _ in range(100):
        body = client.get("/v1/health").json()
        if predicate(body["warmup"]):
            return body
        time.sleep(0.02)
    raise AssertionError(f"warm-up never settled: {body}")


def test_health_reports_ready_after_warmup() -> None:
    node = _Warm()
    with TestClient(_app_with(node)) as client:  # context manager runs the lifespan
        body = _wait_for(client, lambda w: w != "warming")
    assert body["warmup"] == "ready"
    assert body["status"] == "ok"
    assert node.calls == 1


def test_health_reports_failed_warmup_but_stays_live() -> None:
    with TestClient(_app_with(_Warm(fail=True))) as client:
        body = _wait_for(client, lambda w: w != "warming")
        assert body["warmup"] == "failed: model missing"
        assert body["status"] == "ok"  # liveness: requests are still served
        assert (
            client.post(
                "/v1/chat/completions",
                json={"model": "default", "messages": [{"role": "user", "content": "hi"}]},
            ).status_code
            == 200
        )
