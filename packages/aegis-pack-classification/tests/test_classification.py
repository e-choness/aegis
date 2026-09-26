"""Tests for aegis-pack-classification.

Gate: DC uv run pytest packages/aegis-pack-classification -q
"""

from __future__ import annotations

import pytest
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
        node = ClassificationNode(
            patterns=[
                ("top_secret", r"classified"),
                ("public", r".*"),
            ]
        )
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


# ---------------------------------------------------------------------------
# Secret rules — examples written apart from evals/probes.jsonl
# ---------------------------------------------------------------------------

_SECRETS = [
    'curl -H "Authorization: Bearer 9f8e7d6c5b4a39281706f5e4d3c2b1a0ffeeddcc" https://api.example.com',
    '{"client_secret": "Zx9-QwErTy-12345-AbCdE"}',
    "export OPENAI_API_KEY=sk-proj-abc123def456ghi789",
    "mysql://root:toor123@10.0.0.5/prod",
    "Here's the service account key: -----BEGIN PRIVATE KEY----- MIIEvQIBADANBg...",
    "my pwd = Summer2026#",
    "The wifi passphrase is Blue-Falcon-77",
    "SLACK_BOT=xoxb-2203948-11022-AbCdEfGhIjKl",
    "the new password: CorrectHorse9!",
    "creds are admin / P@ssw0rd123",
    "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE",
    "**Authorization Token:** `AUTH-TOK-88902-X-SEC`",
]

_NOT_SECRETS = [
    "The error says: invalid_token, please log in again.",
    "Form validation: password: required, email: required.",
    "Set the TOKEN environment variable before running the tests.",
    "Our password policy: minimum 12 characters, no reuse.",
    "Commit a94a8fe5ccb19ba61c4c0873d391e987982fbbd3 fixed the token refresh bug.",
    'The API returns {"token": null} when the session expires.',
    "Bearer tokens should be sent in the Authorization header.",
    "Use secret: ${{ secrets.NPM_TOKEN }} in the workflow file.",
    "The password is too short, it needs a number.",
    "What does the error 'credentials: not found' mean in the AWS CLI?",
    "Connect with postgres://localhost:5432/app for local dev.",
    "The secret to good bread is patience.",
    "Rotate the api key every 90 days and store it in the vault.",
    "The token count for this prompt is 1,204.",
    "Keys: secret_santa: assigned, gift budget: $30.",
]


@pytest.mark.parametrize("text", _SECRETS)
async def test_secret_shapes_are_labelled_secret(text: str) -> None:
    delta = await ClassificationNode().run(_state(text))
    assert delta.labels == {"classification": "secret"}


@pytest.mark.parametrize("text", _NOT_SECRETS)
async def test_mentions_of_secrets_are_not_secrets(text: str) -> None:
    delta = await ClassificationNode().run(_state(text))
    assert (delta.labels or {}).get("classification") != "secret"


async def test_secret_outranks_pii() -> None:
    delta = await ClassificationNode().run(_state("jane@example.com, password: Winter2026!"))
    assert delta.labels == {"classification": "secret"}
