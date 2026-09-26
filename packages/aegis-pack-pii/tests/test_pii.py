"""Tests for aegis-pack-pii — PiiMaskGuard, PiiMaskNode, PiiUnmaskNode.

Gate: DC uv run pytest packages/aegis-pack-pii -q

Skipped automatically when the [pii] extra is not installed.
"""

from __future__ import annotations

import pytest

pytest.importorskip("presidio_analyzer")

from aegis_pack_pii import PiiMaskGuard, PiiMaskNode, PiiUnmaskNode

from aegis_core.pipeline.state import RunState
from aegis_core.providers.models import Message
from aegis_core.testing.guardrails import GuardrailContractKit

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _state(*contents: str, role: str = "user") -> RunState:
    return RunState(
        run_id="test",
        route="default",
        messages=[Message(role=role, content=c) for c in contents],
    )


# ---------------------------------------------------------------------------
# GuardrailContractKit
# ---------------------------------------------------------------------------


async def test_guard_contract_kit() -> None:
    kit = GuardrailContractKit(PiiMaskGuard())
    await kit.assert_all_async()


# ---------------------------------------------------------------------------
# PiiMaskGuard
# ---------------------------------------------------------------------------


async def test_guard_blocks_pii_email() -> None:
    guard = PiiMaskGuard()
    verdict = await guard.scan(_state("Contact me at john.doe@example.com"))
    assert verdict.is_block
    assert "EMAIL_ADDRESS" in (verdict.reason or "")


async def test_guard_allows_clean_text() -> None:
    guard = PiiMaskGuard()
    verdict = await guard.scan(_state("The sky is blue and the grass is green."))
    assert verdict.is_allow


async def test_guard_blocks_first_message_with_pii() -> None:
    guard = PiiMaskGuard()
    verdict = await guard.scan(
        _state("Hello world", "My email is user@example.com", "Goodbye")
    )
    assert verdict.is_block


# ---------------------------------------------------------------------------
# PiiMaskNode
# ---------------------------------------------------------------------------


async def test_mask_node_masks_email() -> None:
    node = PiiMaskNode()
    state = _state("My email is user@example.com")
    delta = await node.run(state)

    assert delta.messages is not None
    masked_content = delta.messages[-1].content
    assert "user@example.com" not in masked_content
    assert "<EMAIL_ADDRESS_0>" in masked_content

    assert delta.mask_map is not None
    assert "user@example.com" in delta.mask_map.values()


async def test_mask_node_no_pii_returns_empty_delta() -> None:
    node = PiiMaskNode()
    delta = await node.run(_state("Hello, how are you?"))

    assert delta.messages is None
    assert not delta.mask_map


async def test_mask_node_preserves_non_pii_content() -> None:
    node = PiiMaskNode()
    state = _state("My email is user@example.com and the sky is blue.")
    delta = await node.run(state)

    assert delta.messages is not None
    content = delta.messages[0].content
    assert "sky is blue" in content


async def test_mask_node_multiple_entities_unique_placeholders() -> None:
    node = PiiMaskNode()
    state = _state("Email a@example.com and b@example.com")
    delta = await node.run(state)

    assert delta.mask_map is not None
    email_keys = [k for k in delta.mask_map if "EMAIL" in k]
    assert len(email_keys) == 2, f"Expected 2 email placeholders, got: {delta.mask_map}"
    assert email_keys[0] != email_keys[1]


async def test_mask_node_merges_existing_mask_map() -> None:
    node = PiiMaskNode()
    state = RunState(
        run_id="t",
        route="r",
        messages=[Message(role="user", content="Email me at user@example.com")],
        mask_map={"<EXISTING_0>": "existing-value"},
    )
    delta = await node.run(state)

    assert delta.mask_map is not None
    assert "<EXISTING_0>" in delta.mask_map
    assert "existing-value" in delta.mask_map.values()


# ---------------------------------------------------------------------------
# PiiUnmaskNode
# ---------------------------------------------------------------------------


async def test_unmask_node_restores_response() -> None:
    node = PiiUnmaskNode()
    state = RunState(
        run_id="t",
        route="r",
        messages=[],
        response="Thanks, <EMAIL_ADDRESS_0>!",
        mask_map={"<EMAIL_ADDRESS_0>": "user@example.com"},
    )
    delta = await node.run(state)
    assert delta.response == "Thanks, user@example.com!"


async def test_unmask_node_no_op_when_no_mask_map() -> None:
    node = PiiUnmaskNode()
    state = RunState(run_id="t", route="r", messages=[], response="Hello!")
    delta = await node.run(state)
    assert delta.response is None


async def test_unmask_node_no_op_when_no_response() -> None:
    node = PiiUnmaskNode()
    state = RunState(
        run_id="t",
        route="r",
        messages=[],
        mask_map={"<EMAIL_ADDRESS_0>": "user@example.com"},
    )
    delta = await node.run(state)
    assert delta.response is None


# ---------------------------------------------------------------------------
# Round-trip: PiiMaskNode + FakeProvider + PiiUnmaskNode
# ---------------------------------------------------------------------------


async def test_round_trip_pii_never_reaches_provider() -> None:
    """Placeholders replace PII in provider-visible messages; response is unmasked."""
    from aegis_core.pipeline.executor import PipelineExecutor
    from aegis_core.testing.providers import FakeProvider

    # Probe to discover the placeholder name Presidio assigns for the email.
    probe_node = PiiMaskNode()
    probe_state = _state("My email is user@example.com")
    probe_delta = await probe_node.run(probe_state)
    assert probe_delta.mask_map, "Expected PII to be detected in probe"
    # Pick the EMAIL_ADDRESS placeholder specifically (deduplication keeps it).
    placeholder = next(
        k for k in probe_delta.mask_map if "EMAIL" in k
    )

    # FakeProvider echoes back a response containing the placeholder
    fake = FakeProvider(complete_response=f"Got it, {placeholder}")
    ex = PipelineExecutor()
    ex.register(
        "pii-route",
        provider=fake,
        ingress=[PiiMaskNode()],
        egress=[PiiUnmaskNode()],
    )

    initial = RunState(
        run_id="round-trip",
        route="pii-route",
        messages=[Message(role="user", content="My email is user@example.com")],
    )
    result = await ex.run("pii-route", initial)

    # Provider must NOT have seen the raw email address
    assert fake.complete_calls, "FakeProvider was never called"
    provider_content = " ".join(m.content for m in fake.complete_calls[0].messages)
    assert "user@example.com" not in provider_content, (
        f"Raw PII reached the provider: {provider_content!r}"
    )

    # Final response must contain the restored original email
    assert result.response == "Got it, user@example.com"


# ---------------------------------------------------------------------------
# Constructor `name` override (used by from_config to namespace declarations)
# ---------------------------------------------------------------------------


def test_mask_node_accepts_name_override() -> None:
    node = PiiMaskNode(name="pii.mask")
    assert node.name == "pii.mask"


def test_mask_node_default_name_unchanged() -> None:
    assert PiiMaskNode().name == "pii_mask_node"


def test_unmask_node_accepts_name_override() -> None:
    node = PiiUnmaskNode(name="pii.unmask")
    assert node.name == "pii.unmask"


def test_unmask_node_default_name_unchanged() -> None:
    assert PiiUnmaskNode().name == "pii_unmask_node"


# ---------------------------------------------------------------------------
# from_config factory — must actually be callable from aegis.yaml
# ---------------------------------------------------------------------------


class TestPiiFactory:
    def test_mask_mode_returns_ingress_and_egress_nodes(self) -> None:
        from aegis_pack_pii.factory import from_config

        from aegis_core.config.models import GuardrailConfig

        result = from_config("pii", GuardrailConfig(pack="aegis.pii", mode="mask"))
        assert set(result.keys()) == {"ingress", "egress"}
        assert isinstance(result["ingress"][0], PiiMaskNode)
        assert isinstance(result["egress"][0], PiiUnmaskNode)
        assert result["ingress"][0].name == "pii.mask"
        assert result["egress"][0].name == "pii.unmask"

    def test_detect_mode_returns_guard_node(self) -> None:
        from aegis_pack_pii.factory import from_config

        from aegis_core.config.models import GuardrailConfig

        result = from_config("pii", GuardrailConfig(pack="aegis.pii", mode="detect"))
        assert set(result.keys()) == {"ingress"}

    def test_unknown_mode_raises_config_error(self) -> None:
        from aegis_pack_pii.factory import from_config

        from aegis_core.config.models import GuardrailConfig
        from aegis_core.errors import AegisConfigValidationError

        with pytest.raises(AegisConfigValidationError):
            from_config("pii", GuardrailConfig(pack="aegis.pii", mode="nope"))


# ---------------------------------------------------------------------------
# Detection accuracy: curated entities, threshold, allow-list, Canadian SIN
# ---------------------------------------------------------------------------


def _types(text: str, **options: object) -> list[str]:
    from aegis_pack_pii import PiiDetector

    detector = PiiDetector.from_options(**options)  # type: ignore[arg-type]
    return sorted(r.entity_type for r in detector.find(text))


class TestDetectionAccuracy:
    def test_common_words_are_not_masked_by_default(self) -> None:
        assert _types("Please send the quarterly summary on Monday for vendor 7731.") == []

    def test_identifying_entities_still_masked(self) -> None:
        found = _types("Mail jane.doe@example.com, call 416-555-0199, card 4111 1111 1111 1111.")
        assert found == ["CREDIT_CARD", "EMAIL_ADDRESS", "PHONE_NUMBER"]

    def test_email_is_not_split_into_url_fragments(self) -> None:
        assert _types("Reply to jane.doe@example.com") == ["EMAIL_ADDRESS"]

    def test_canadian_sin_detected_and_luhn_checked(self) -> None:
        assert _types("Applicant SIN is 046-454-286.") == ["CA_SIN"]
        assert "CA_SIN" not in _types("Applicant SIN is 046-454-287.")

    def test_date_time_is_opt_in(self) -> None:
        text = "Born on 1984-03-12."
        assert "DATE_TIME" not in _types(text)
        assert "DATE_TIME" in _types(text, entities=["DATE_TIME"])

    def test_all_entities(self) -> None:
        assert "DATE_TIME" in _types("See you on Monday.", entities="ALL")

    def test_allow_list(self) -> None:
        assert _types("Ask Claude about it.", allow_list=["Claude"]) == []

    def test_threshold_filters_low_confidence(self) -> None:
        # Phone numbers without context score 0.40.
        assert _types("416-555-0199", threshold=0.5) == []
        assert _types("416-555-0199", threshold=0.4) == ["PHONE_NUMBER"]

    def test_unknown_entity_rejected(self) -> None:
        from aegis_pack_pii import PiiDetector

        with pytest.raises(ValueError, match="unknown PII entities"):
            PiiDetector.from_options(entities=["NOT_A_THING"])

    def test_threshold_out_of_range_rejected(self) -> None:
        from aegis_pack_pii import PiiDetector

        with pytest.raises(ValueError, match="between 0 and 1"):
            PiiDetector.from_options(threshold=1.5)


class TestFactoryDetectionOptions:
    def _cfg(self, **options: object):  # type: ignore[no-untyped-def]
        from aegis_core.config.models import GuardrailConfig

        return GuardrailConfig.model_validate({"pack": "aegis.pii", **options})

    async def test_options_reach_the_mask_node(self) -> None:
        from aegis_pack_pii.factory import from_config

        nodes = from_config("pii", self._cfg(entities=["EMAIL_ADDRESS"], allow_list=["ops@example.com"]))
        state = RunState(
            run_id="r",
            route="default",
            messages=[Message(role="user", content="ops@example.com and jane@example.com, 416-555-0199")],
        )
        delta = await nodes["ingress"][0].run(state)
        assert delta.messages is not None
        assert delta.messages[0].content == "ops@example.com and <EMAIL_ADDRESS_0>, 416-555-0199"

    def test_bad_options_raise_config_error(self) -> None:
        from aegis_pack_pii.factory import from_config

        from aegis_core.errors import AegisConfigValidationError

        with pytest.raises(AegisConfigValidationError, match="unknown PII entities"):
            from_config("pii", self._cfg(entities=["NOPE"]))


class TestPlaceholderConsistency:
    async def test_same_value_gets_same_placeholder_across_messages(self) -> None:
        state = RunState(
            run_id="r",
            route="default",
            messages=[
                Message(role="user", content="Please write to jane@example.com and bob@example.com."),
                Message(role="user", content="Did jane@example.com reply?"),
            ],
        )
        delta = await PiiMaskNode().run(state)
        assert delta.messages is not None
        assert delta.messages[0].content == "Please write to <EMAIL_ADDRESS_0> and <EMAIL_ADDRESS_1>."
        assert delta.messages[1].content == "Did <EMAIL_ADDRESS_0> reply?"
        assert delta.mask_map == {
            "<EMAIL_ADDRESS_0>": "jane@example.com",
            "<EMAIL_ADDRESS_1>": "bob@example.com",
        }

    async def test_existing_mask_map_is_never_overwritten(self) -> None:
        state = RunState(
            run_id="r",
            route="default",
            messages=[Message(role="user", content="Also cc carol@example.com and jane@example.com.")],
            mask_map={"<EMAIL_ADDRESS_0>": "jane@example.com"},
        )
        delta = await PiiMaskNode().run(state)
        assert delta.messages is not None
        assert delta.messages[0].content == "Also cc <EMAIL_ADDRESS_1> and <EMAIL_ADDRESS_0>."
        assert delta.mask_map == {
            "<EMAIL_ADDRESS_0>": "jane@example.com",
            "<EMAIL_ADDRESS_1>": "carol@example.com",
        }


class TestSpacyModel:
    """The pack must never download a model at runtime (fails in read-only containers)."""

    def test_default_model_is_the_small_one(self) -> None:
        from aegis_pack_pii import PiiDetector
        from aegis_pack_pii._engine import get_analyzer

        assert PiiDetector().spacy_model == "en_core_web_sm"
        from presidio_analyzer.nlp_engine import SpacyNlpEngine

        nlp_engine = get_analyzer().nlp_engine
        assert isinstance(nlp_engine, SpacyNlpEngine)
        assert nlp_engine.nlp is not None
        assert [n.meta["name"] for n in nlp_engine.nlp.values()] == ["core_web_sm"]

    def test_missing_model_fails_with_install_command(self) -> None:
        from aegis_pack_pii import PiiDetector

        with pytest.raises(ValueError, match="python -m spacy download xx_not_a_model"):
            PiiDetector.from_options(spacy_model="xx_not_a_model")

    def test_missing_model_is_a_startup_config_error(self) -> None:
        from aegis_pack_pii.factory import from_config

        from aegis_core.config.models import GuardrailConfig
        from aegis_core.errors import AegisConfigValidationError

        cfg = GuardrailConfig.model_validate({"pack": "aegis.pii", "spacy_model": "xx_not_a_model"})
        with pytest.raises(AegisConfigValidationError, match="not installed"):
            from_config("pii", cfg)
