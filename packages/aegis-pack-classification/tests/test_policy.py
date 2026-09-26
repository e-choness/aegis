"""Tests for the label policy guard (pack: aegis.policy)."""

from __future__ import annotations

import textwrap
import uuid
from pathlib import Path

import pytest
from aegis_pack_classification import LabelPolicyGuard, PolicyRule
from aegis_pack_classification.factory import policy_from_config

from aegis_core.config.models import GuardrailConfig
from aegis_core.errors import AegisConfigValidationError
from aegis_core.pipeline.state import RunState
from aegis_core.pipeline.verdict import VerdictKind
from aegis_core.providers.models import Message


def _state(**labels: str) -> RunState:
    return RunState(run_id="t", route="r", messages=[], labels=dict(labels))


def _rule(raw: dict) -> PolicyRule:  # type: ignore[type-arg]
    return PolicyRule.from_dict(raw)


SECRET_BLOCK = {"when": {"label": "classification", "in": ["secret"]}, "verdict": "block"}
PII_APPROVE = {
    "when": {"label": "classification", "in": ["pii", "financial"]},
    "verdict": "require_approval",
    "reason": "personal data needs sign-off",
}


class TestRules:
    async def test_first_matching_rule_wins(self) -> None:
        guard = LabelPolicyGuard([_rule(SECRET_BLOCK), _rule(PII_APPROVE)])
        blocked = await guard.scan(_state(classification="secret"))
        paused = await guard.scan(_state(classification="financial"))
        assert blocked.kind == VerdictKind.BLOCK
        assert blocked.reason == "policy: classification is 'secret'"
        assert paused.kind == VerdictKind.REQUIRE_APPROVAL
        assert paused.prompt == "personal data needs sign-off"

    async def test_no_match_or_missing_label_allows(self) -> None:
        guard = LabelPolicyGuard([_rule(SECRET_BLOCK)])
        assert (await guard.scan(_state(classification="public"))).kind == VerdictKind.ALLOW
        assert (await guard.scan(_state())).kind == VerdictKind.ALLOW

    async def test_allow_rule_short_circuits_later_rules(self) -> None:
        allow = {"when": {"label": "route_tier", "in": "internal"}, "verdict": "allow"}
        guard = LabelPolicyGuard([_rule(allow), _rule(SECRET_BLOCK)])
        verdict = await guard.scan(_state(route_tier="internal", classification="secret"))
        assert verdict.kind == VerdictKind.ALLOW

    async def test_min_confidence_uses_recorded_confidence(self) -> None:
        rule = _rule(
            {
                "when": {"label": "sensitivity", "in": ["confidential"], "min_confidence": 0.8},
                "verdict": "require_approval",
            }
        )
        guard = LabelPolicyGuard([rule])
        unsure = _state(sensitivity="confidential", **{"sensitivity.confidence": "0.55"})
        sure = _state(sensitivity="confidential", **{"sensitivity.confidence": "0.93"})
        unscored = _state(sensitivity="confidential")  # regex labels carry no confidence
        assert (await guard.scan(unsure)).kind == VerdictKind.ALLOW
        assert (await guard.scan(sure)).kind == VerdictKind.REQUIRE_APPROVAL
        assert (await guard.scan(unscored)).kind == VerdictKind.REQUIRE_APPROVAL

    @pytest.mark.parametrize(
        ("raw", "message"),
        [
            ({"verdict": "block"}, "each rule needs"),
            ({"when": {"label": "x"}, "verdict": "block"}, "each rule needs"),
            ({"when": {"label": "x", "in": ["y"]}, "verdict": "deny"}, "verdict must be one of"),
            (
                {"when": {"label": "x", "in": ["y"], "min_confidence": 2}, "verdict": "block"},
                "between 0 and 1",
            ),
        ],
    )
    def test_invalid_rules_rejected(self, raw: dict, message: str) -> None:  # type: ignore[type-arg]
        with pytest.raises(ValueError, match=message):
            PolicyRule.from_dict(raw)


class TestFactory:
    def test_requires_rules(self) -> None:
        with pytest.raises(AegisConfigValidationError, match="non-empty 'rules'"):
            policy_from_config("p", GuardrailConfig(pack="aegis.policy"))

    def test_bad_rule_is_a_config_error(self) -> None:
        cfg = GuardrailConfig.model_validate(
            {"pack": "aegis.policy", "rules": [{"when": {"label": "a", "in": ["b"]}}]}
        )
        with pytest.raises(AegisConfigValidationError, match=r"invalid aegis.policy rule"):
            policy_from_config("p", cfg)


async def test_classified_memo_blocked_end_to_end(tmp_path: Path) -> None:
    """classification labels, policy decides — wired entirely from aegis.yaml."""
    from aegis_core.config.build import build_executor
    from aegis_core.config.loader import load_config

    path = tmp_path / "aegis.yaml"
    path.write_text(
        textwrap.dedent(
            """
            providers:
              fake: {type: fake}
            guardrails:
              classify: {pack: aegis.classification}
              content_policy:
                pack: aegis.policy
                rules:
                  - when: {label: classification, in: [secret]}
                    verdict: block
                    reason: credentials must not reach a model
            routes:
              default:
                provider: fake
                pipeline: {ingress: [classify, content_policy]}
            """
        )
    )
    executor = build_executor(load_config(path))

    async def run(text: str) -> RunState:
        state = RunState(
            run_id=str(uuid.uuid4()), route="default", messages=[Message(role="user", content=text)]
        )
        return await executor.run("default", state)

    blocked = await run("**Authorization Token:** `AUTH-TOK-88902-X-SEC`")
    allowed = await run("What's the weather in Toronto?")
    assert blocked.status == "blocked"
    assert any(
        e.data.get("reason") == "credentials must not reach a model" for e in blocked.events
    )
    assert allowed.status == "completed"
