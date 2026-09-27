"""The Hugging Face demo config (deploy/huggingface/aegis.yaml) does what its tabs promise.

The content model is stubbed with a keyword model, so this runs in CI without
weights; the real model's behaviour is measured by scripts/eval_guards.py.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
import yaml

from aegis_core.config.build import build_executor
from aegis_core.config.loader import load_config
from aegis_core.pipeline.checkpointer import make_memory_checkpointer
from aegis_core.pipeline.executor import PipelineExecutor
from aegis_core.pipeline.state import RunState
from aegis_core.providers.models import Message
from aegis_server.showcase_tabs import build_showcase

ROOT = Path(__file__).parents[3]
DEMO = ROOT / "deploy" / "huggingface" / "aegis.yaml"
EVAL = ROOT / "evals" / "content.yaml"


class _KeywordModel:
    def __init__(
        self, model_id: str | None = None, options: Mapping[str, Any] | None = None
    ) -> None:
        pass

    def warmup(self) -> None:
        pass

    def analyze(self, text: str, entities: Mapping[str, str], tasks: Mapping[str, Sequence[str]]):  # type: ignore[no-untyped-def]
        from aegis_pack_content import Analysis, Entity, Label

        found = [
            Entity(m.start(), m.end(), label, 0.99)
            for label in entities
            for m in re.finditer(r"\b[\w-]+\.corp\.internal\b", text)
        ]
        attack = "ignore all previous" in text.lower() or "pretend you are dan" in text.lower()
        labels = {
            task: Label(values[1] if attack else values[0], 0.99) for task, values in tasks.items()
        }
        return Analysis(entities=found, labels=labels)


@pytest.fixture
def executor(monkeypatch: pytest.MonkeyPatch) -> PipelineExecutor:
    import aegis_pack_content.factory as factory
    import aegis_pack_content.gliner as gliner

    monkeypatch.setattr(gliner, "ensure_installed", lambda: None)
    monkeypatch.setattr(factory, "load_backend", lambda *_a, **_k: _KeywordModel())
    return build_executor(load_config(DEMO), checkpointer=make_memory_checkpointer())


def _presets() -> list[tuple[str, str, str]]:
    tabs = build_showcase(load_config(DEMO))
    return [
        (r["route"], p["label"], p["prompt"])
        for t in tabs
        for r in t["routes"]
        for p in r["presets"]
    ]


# route, preset label → status the tab promises (model-dependent presets use the stub).
EXPECTED = {
    ("privacy", "Email + SIN"): "completed",
    ("privacy", "Home address"): "completed",
    ("privacy", "Internal hostname"): "completed",
    ("privacy", "Nothing to hide"): "completed",
    ("policy", "Classified memo (token inside)"): "blocked",
    ("policy", "API key"): "blocked",
    ("policy", "Card number"): "paused",
    ("policy", "Everyday question"): "completed",
    ("attacks", "Ignore your instructions"): "paused",
    ("attacks", "Jailbreak role-play"): "paused",
    ("attacks", "Ordinary question"): "completed",
    ("underwriting", "No personal data"): "completed",
    ("underwriting", "Applicant with a SIN"): "paused",
    ("underwriting", "Card on file"): "paused",
    ("agent", "Harmless request"): "paused",
    ("agent_poisoned", "Harmless request"): "blocked",
    ("metered", "Spend a cent"): "completed",
}


async def _run(
    executor: PipelineExecutor, route: str, prompt: str, principal: str = "v"
) -> RunState:
    state = RunState(
        run_id=str(uuid.uuid4()),
        route=route,
        messages=[Message(role="user", content=prompt)],
        principal=principal,
    )
    return await executor.run(route, state)


async def test_every_preset_does_what_its_tab_says(executor: PipelineExecutor) -> None:
    presets = _presets()
    covered = {(route, label) for route, label, _ in presets}
    assert set(EXPECTED) <= covered, set(EXPECTED) - covered
    for route, label, prompt in presets:
        if (route, label) in EXPECTED:
            result = await _run(executor, route, prompt)
            assert result.status == EXPECTED[(route, label)], (route, label, result.events)


async def test_privacy_masks_rules_and_model_entities(executor: PipelineExecutor) -> None:
    result = await _run(
        executor, "privacy", "billing-api.corp.internal — ask priya@example.com, SIN 046 454 286"
    )
    types = {p.strip("<>").rsplit("_", 1)[0] for p in result.mask_map}
    assert {"INTERNAL_HOSTNAME", "EMAIL_ADDRESS", "CA_SIN"} <= types
    assert result.response is not None
    assert "<" not in result.response  # everything unmasked on the way back


async def test_approving_the_agent_sends_the_email(executor: PipelineExecutor) -> None:
    state = RunState(
        run_id=str(uuid.uuid4()),
        route="agent",
        messages=[Message(role="user", content="Summarise our refund policy for me.")],
    )
    assert (await executor.run("agent", state)).status == "paused"
    resumed = await executor.resume(state.run_id, "agent", {"decision": "approved"})
    assert resumed.status == "completed"


async def test_budget_blocks_the_sixth_run_per_visitor(executor: PipelineExecutor) -> None:
    statuses = [(await _run(executor, "metered", "hi", principal="alice")).status for _ in range(6)]
    assert statuses == ["completed"] * 5 + ["blocked"]
    assert (await _run(executor, "metered", "hi", principal="bob")).status == "completed"


def test_demo_content_settings_are_the_measured_ones() -> None:
    demo = yaml.safe_load(DEMO.read_text(encoding="utf-8"))["guardrails"]
    measured = yaml.safe_load(EVAL.read_text(encoding="utf-8"))["guardrails"]["content"]
    content = [g for g in demo.values() if g["pack"] == "aegis.content"]
    assert {g["model"] for g in content} == {measured["model"]}
    assert {g["threshold"] for g in content} == {measured["threshold"]}
    merged_entities = {k: v for g in content for k, v in (g.get("entities") or {}).items()}
    merged_labels = {k: v for g in content for k, v in (g.get("labels") or {}).items()}
    assert merged_entities == measured["entities"]
    assert merged_labels == measured["labels"]
