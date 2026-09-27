"""Tests for aegis_core.masking — the placeholder scheme every masking pack shares."""

from __future__ import annotations

from aegis_core.masking import Found, Placeholders, UnmaskNode, mask_messages, mask_text, unmask
from aegis_core.pipeline.state import RunState
from aegis_core.providers.models import Message


def _state(*texts: str, mask_map: dict[str, str] | None = None) -> RunState:
    return RunState(
        run_id="r",
        route="x",
        messages=[Message(role="user", content=t) for t in texts],
        mask_map=dict(mask_map or {}),
    )


def _finder(**by_value: str):  # type: ignore[no-untyped-def]
    """Find every occurrence of each value, labelled with its entity type."""

    def find(text: str) -> list[Found]:
        found = []
        for value, etype in by_value.items():
            start = text.find(value)
            while start != -1:
                found.append(Found(start, start + len(value), etype))
                start = text.find(value, start + 1)
        return found

    return find


def test_same_value_same_placeholder_numbered_in_reading_order() -> None:
    text = "b@x.io wrote to a@x.io, then b@x.io again"
    spans = _finder(**{"a@x.io": "EMAIL", "b@x.io": "EMAIL"})(text)
    masked, found = mask_text(text, spans, Placeholders({}))
    assert masked == "<EMAIL_0> wrote to <EMAIL_1>, then <EMAIL_0> again"
    assert found == {"<EMAIL_0>": "b@x.io", "<EMAIL_1>": "a@x.io"}


def test_existing_placeholders_are_reused_and_numbering_continues() -> None:
    state = _state("tok-1 and tok-2", mask_map={"<CREDENTIAL_0>": "tok-1"})
    delta = mask_messages(state, _finder(**{"tok-1": "CREDENTIAL", "tok-2": "CREDENTIAL"}))
    assert delta.messages is not None
    assert delta.messages[0].content == "<CREDENTIAL_0> and <CREDENTIAL_1>"
    assert delta.mask_map == {"<CREDENTIAL_0>": "tok-1", "<CREDENTIAL_1>": "tok-2"}


def test_spans_over_an_existing_placeholder_are_skipped() -> None:
    # A second pack that "detects" part of another pack's placeholder must not re-mask it.
    text = "email <EMAIL_ADDRESS_0> now"
    spans = [Found(6, 23, "CREDENTIAL"), Found(0, 5, "WORD")]
    masked, found = mask_text(text, spans, Placeholders({"<EMAIL_ADDRESS_0>": "a@x.io"}))
    assert masked == "<WORD_0> <EMAIL_ADDRESS_0> now"
    assert found == {"<WORD_0>": "email"}


def test_nothing_found_is_an_empty_delta() -> None:
    delta = mask_messages(_state("hello"), lambda _t: [])
    assert delta.messages is None
    assert delta.mask_map is None


async def test_unmask_node_restores_everything_and_is_idempotent() -> None:
    mask_map = {"<A_0>": "alpha", "<B_0>": "beta"}
    assert unmask("<A_0> and <B_0>", mask_map) == "alpha and beta"
    state = _state(mask_map=mask_map)
    state.response = "<A_0>/<B_0>"
    delta = await UnmaskNode().run(state)
    assert delta.response == "alpha/beta"
    state.response = delta.response
    assert (await UnmaskNode().run(state)).response == "alpha/beta"
