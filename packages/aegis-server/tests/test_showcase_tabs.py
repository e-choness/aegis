"""Showcase tabs are built from the config; showcase runs join the audit trail."""

from __future__ import annotations

import textwrap
from pathlib import Path

import yaml
from starlette.testclient import TestClient

from aegis_core.config.loader import load_config
from aegis_core.pipeline.executor import PipelineExecutor
from aegis_core.testing.providers import FakeProvider
from aegis_server.app import create_app
from aegis_server.showcase_tabs import build_showcase, route_yaml
from aegis_server.store.ledger import InMemoryLedgerStore
from aegis_server.store.run_store import InMemoryRunStore

CONFIG = """
providers:
  llm: {type: openai_compatible, base_url: "http://x/v1", model: m, api_key: sk-secret-value}
  fake: {type: fake}
guardrails:
  classify: {pack: aegis.classification}
  unused: {pack: aegis.classification}
routes:
  b_route:
    provider: fake
    pipeline: {ingress: [classify]}
    showcase:
      tab: second
      title: Second
      order: 2
      presets: [{label: Hi, prompt: hello}, {label: empty}]
  a_route:
    provider: llm
    showcase: {tab: first, title: First, order: 1, blurb: Starts here, label: Route A}
  a_other:
    provider: fake
    showcase: {tab: first, label: Other}
  hidden:
    provider: fake
"""


def _cfg(tmp_path: Path, text: str = CONFIG):  # type: ignore[no-untyped-def]
    path = tmp_path / "aegis.yaml"
    path.write_text(textwrap.dedent(text))
    return load_config(path)


def test_tabs_grouped_ordered_and_curated(tmp_path: Path) -> None:
    tabs = build_showcase(_cfg(tmp_path))
    assert [t["id"] for t in tabs] == ["first", "second"]
    first = tabs[0]
    assert first["title"] == "First"
    assert first["blurb"] == "Starts here"
    assert [(r["route"], r["label"]) for r in first["routes"]] == [
        ("a_route", "Route A"),
        ("a_other", "Other"),
    ]
    # presets without a prompt are dropped; "hidden" has no showcase block, so no tab
    assert tabs[1]["routes"][0]["presets"] == [{"label": "Hi", "prompt": "hello"}]


def test_route_yaml_shows_only_what_the_route_uses_with_secrets_redacted(tmp_path: Path) -> None:
    snippet = yaml.safe_load(route_yaml(_cfg(tmp_path), "b_route"))
    assert snippet == {
        "providers": {"fake": {"type": "fake"}},
        "guardrails": {"classify": {"pack": "aegis.classification"}},
        "routes": {"b_route": {"provider": "fake", "pipeline": {"ingress": ["classify"]}}},
    }
    secret = route_yaml(_cfg(tmp_path), "a_route")
    assert "sk-secret-value" not in secret
    assert "REDACTED" in secret


def test_without_showcase_blocks_every_route_gets_a_tab(tmp_path: Path) -> None:
    cfg = _cfg(
        tmp_path,
        "providers: {fake: {type: fake}}\nroutes: {x: {provider: fake}, y: {provider: fake}}\n",
    )
    assert [t["id"] for t in build_showcase(cfg)] == ["x", "y"]


def _client(**kwargs: object) -> TestClient:
    executor = PipelineExecutor()
    executor.register(
        "default", provider=FakeProvider(complete_response="ok", cost_per_request=0.02)
    )
    return TestClient(create_app(executor, no_auth=True, run_store=InMemoryRunStore(), **kwargs))  # type: ignore[arg-type]


def test_tabs_endpoint_falls_back_to_routes() -> None:
    tabs = _client().get("/showcase/api/tabs").json()["tabs"]
    assert [t["id"] for t in tabs] == ["default"]


def test_tabs_endpoint_serves_configured_tabs() -> None:
    tabs = [{"id": "t", "title": "T", "order": 1, "blurb": "", "routes": []}]
    assert _client(showcase_tabs=tabs).get("/showcase/api/tabs").json()["tabs"] == tabs


def test_showcase_runs_are_recorded_like_api_runs() -> None:
    ledger = InMemoryLedgerStore()
    with _client(ledger_store=ledger) as client:
        body = client.post("/showcase/api/invoke", json={"prompt": "hi", "route": "default"}).json()
        assert body["cost"] == 0.02
        run = client.get(f"/v1/runs/{body['run_id']}").json()
        assert run["events"]  # explainable from the Audit tab
        records = client.get("/v1/audit/ledger").json()["records"]
        assert any(r.get("run_id") == body["run_id"] for r in records)
        assert client.get("/v1/audit/verify").json()["intact"] is True


def test_page_is_served_from_the_static_file() -> None:
    page = _client().get("/showcase").text
    assert "Pipeline Showcase" in page
    assert "/showcase/api/tabs" in page
