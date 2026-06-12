"""Tests for aegis-pack-classification.

Gate: DC uv run pytest packages/aegis-pack-classification -q
"""

from __future__ import annotations

from aegis_pack_classification import ClassificationNode

from aegis_core.pipeline.state import RunState
from aegis_core.providers.models import Message

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
# ClassificationNode — basic labeling
# ---------------------------------------------------------------------------


class TestClassificationNode:
    async def test_classifies_email_as_pii(self) -> None:
        node = ClassificationNode()
        delta = await node.run(_state("My email is alice@example.com"))
        assert delta.labels is not None
        assert delta.labels["classification"] == "pii"

    async def test_classifies_phone_as_pii(self) -> None:
        node = ClassificationNode()
        delta = await node.run(_state("Call me at 555-867-5309"))
        assert delta.labels is not None
        assert delta.labels["classification"] == "pii"

    async def test_classifies_credit_card_as_financial(self) -> None:
        node = ClassificationNode()
        delta = await node.run(_state("Card: 4111 1111 1111 1111"))
        assert delta.labels is not None
        assert delta.labels["classification"] == "financial"

    async def test_classifies_api_key_as_secret(self) -> None:
        node = ClassificationNode()
        delta = await node.run(_state("api_key=sk-abc123"))
        assert delta.labels is not None
        assert delta.labels["classification"] == "secret"

    async def test_classifies_password_as_secret(self) -> None:
        node = ClassificationNode()
        delta = await node.run(_state("password: hunter2"))
        assert delta.labels is not None
        assert delta.labels["classification"] == "secret"

    async def test_classifies_medical(self) -> None:
        node = ClassificationNode()
        delta = await node.run(_state("Patient diagnosis: hypertension"))
        assert delta.labels is not None
        assert delta.labels["classification"] == "medical"

    async def test_classifies_legal(self) -> None:
        node = ClassificationNode()
        delta = await node.run(_state("This is attorney-client privileged"))
        assert delta.labels is not None
        assert delta.labels["classification"] == "legal"

    async def test_classifies_plain_text_as_public(self) -> None:
        node = ClassificationNode()
        delta = await node.run(_state("What is the weather today?"))
        assert delta.labels is not None
        assert delta.labels["classification"] == "public"

    async def test_uses_last_user_message(self) -> None:
        node = ClassificationNode()
        state = RunState(
            run_id="r",
            route="d",
            messages=[
                Message(role="user", content="What is the weather?"),
                Message(role="assistant", content="It is sunny."),
                Message(role="user", content="My email is bob@test.com"),
            ],
        )
        delta = await node.run(state)
        assert delta.labels is not None
        assert delta.labels["classification"] == "pii"

    async def test_no_user_message_returns_empty_delta(self) -> None:
        node = ClassificationNode()
        state = RunState(
            run_id="r",
            route="d",
            messages=[Message(role="assistant", content="hello")],
        )
        delta = await node.run(state)
        assert delta.labels is None

    async def test_custom_patterns_first_match_wins(self) -> None:
        node = ClassificationNode(patterns=[
            ("top_secret", r"classified"),
            ("public", r".*"),
        ])
        delta = await node.run(_state("This document is classified"))
        assert delta.labels is not None
        assert delta.labels["classification"] == "top_secret"

    async def test_no_match_with_empty_patterns(self) -> None:
        node = ClassificationNode(patterns=[])
        delta = await node.run(_state("anything"))
        assert delta.labels is None

    def test_node_name_default(self) -> None:
        node = ClassificationNode()
        assert node.name == "classification"

    def test_node_name_custom(self) -> None:
        node = ClassificationNode(name="my_classifier")
        assert node.name == "my_classifier"
