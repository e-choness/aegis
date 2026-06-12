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
