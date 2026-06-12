"""Tests for SSE streaming on /v1/chat/completions (PROJECT_SPEC D12).

Gate: DC uv run pytest packages/aegis-server packages/aegis-core -q -k stream
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import ClassVar, Literal

from starlette.testclient import TestClient

from aegis_core.guardrails import GuardNode, RegexGuard
from aegis_core.guardrails.protocol import Guardrail
from aegis_core.pipeline.executor import PipelineExecutor
from aegis_core.pipeline.state import RunState
from aegis_core.pipeline.verdict import Verdict
from aegis_core.testing.providers import FakeProvider
from aegis_server.app import create_app

# ---------------------------------------------------------------------------
# Incremental guard fixtures
# ---------------------------------------------------------------------------


class _AllowIncrementalGuard:
    name = "allow_incremental"
    streaming: ClassVar[Literal["none", "incremental"]] = "incremental"

    async def scan(self, state: RunState) -> Verdict:
        return Verdict.allow()

    async def scan_chunk(self, chunk: str) -> Verdict:
        return Verdict.allow()

    async def finalize(self, accumulated: str) -> Verdict:
        return Verdict.allow()


class _LateViolationGuard:
    """Passes all chunks but blocks in finalize."""

    name = "late_violation"
    streaming: ClassVar[Literal["none", "incremental"]] = "incremental"

    async def scan(self, state: RunState) -> Verdict:
        return Verdict.allow()

    async def scan_chunk(self, chunk: str) -> Verdict:
        return Verdict.allow()

    async def finalize(self, accumulated: str) -> Verdict:
        return Verdict.block("late violation: forbidden content detected")


class _ChunkBlockGuard:
    """Blocks when a specific token appears in a chunk."""

    name = "chunk_blocker"
    streaming: ClassVar[Literal["none", "incremental"]] = "incremental"

    def __init__(self, forbidden: str) -> None:
        self._forbidden = forbidden

    async def scan(self, state: RunState) -> Verdict:
        return Verdict.allow()

    async def scan_chunk(self, chunk: str) -> Verdict:
        if self._forbidden in chunk:
            return Verdict.block(f"chunk contains forbidden token: {self._forbidden!r}")
        return Verdict.allow()

    async def finalize(self, accumulated: str) -> Verdict:
        return Verdict.allow()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_sse(text: str) -> list[dict]:
    """Parse raw SSE response body into a list of data payloads."""
    results = []
    for line in text.splitlines():
        if line.startswith("data: "):
            raw = line[6:].strip()
            if raw == "[DONE]":
                results.append({"_done": True})
            else:
                results.append(json.loads(raw))
    return results


def _make_streaming_client(
    *,
    route: str = "default",
    egress_guards: list[Guardrail] | None = None,
    stream_chunks: list[str] | None = None,
) -> tuple[TestClient, FakeProvider]:
    """Build a no-auth TestClient with a single route."""
    chunks = stream_chunks or ["hello", " from", " fake"]
    fake = FakeProvider(stream_chunks=chunks)
    executor = PipelineExecutor()
    if egress_guards:
        egress_node = GuardNode(egress_guards, name="egress")
        executor.register(route, provider=fake, egress=[egress_node])
    else:
        executor.register(route, provider=fake)
    app = create_app(executor, no_auth=True)
    return TestClient(app, raise_server_exceptions=True), fake


# ---------------------------------------------------------------------------
# TestTrueStreamingRoute
# ---------------------------------------------------------------------------


class TestTrueStreamingRoute:
    """A route with all-incremental egress guards truly streams."""

    def test_returns_sse_content_type(self) -> None:
        client, _ = _make_streaming_client(
            egress_guards=[_AllowIncrementalGuard()],
        )
        resp = client.post(
            "/v1/chat/completions",
            json={"model": "default", "messages": [{"role": "user", "content": "hi"}], "stream": True},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

    def test_chunk_cadence_multiple_frames(self) -> None:
        """Each provider chunk becomes its own SSE data frame."""
        client, _ = _make_streaming_client(
            egress_guards=[_AllowIncrementalGuard()],
            stream_chunks=["chunk1", " chunk2", " chunk3"],
        )
        resp = client.post(
            "/v1/chat/completions",
            json={"model": "default", "messages": [{"role": "user", "content": "hi"}], "stream": True},
        )
        frames = _parse_sse(resp.text)
        # Each chunk + a stop frame + [DONE]
        chunk_frames = [f for f in frames if not f.get("_done") and f.get("choices", [{}])[0].get("delta", {}).get("content")]
        assert len(chunk_frames) == 3

    def test_frames_are_valid_openai_sse(self) -> None:
        client, _ = _make_streaming_client(
            egress_guards=[_AllowIncrementalGuard()],
        )
        resp = client.post(
            "/v1/chat/completions",
            json={"model": "default", "messages": [{"role": "user", "content": "hi"}], "stream": True},
        )
        frames = _parse_sse(resp.text)
        data_frames = [f for f in frames if not f.get("_done")]
        for frame in data_frames:
            assert "id" in frame
            assert frame["id"].startswith("chatcmpl-")
            assert frame["object"] == "chat.completion.chunk"
            assert "choices" in frame

    def test_ends_with_done(self) -> None:
        client, _ = _make_streaming_client(
            egress_guards=[_AllowIncrementalGuard()],
        )
        resp = client.post(
            "/v1/chat/completions",
            json={"model": "default", "messages": [{"role": "user", "content": "hi"}], "stream": True},
        )
        frames = _parse_sse(resp.text)
        assert frames[-1] == {"_done": True}

    def test_provider_stream_called_not_complete(self) -> None:
        client, fake = _make_streaming_client(
            egress_guards=[_AllowIncrementalGuard()],
        )
        client.post(
            "/v1/chat/completions",
            json={"model": "default", "messages": [{"role": "user", "content": "hi"}], "stream": True},
        )
        assert len(fake.stream_calls) == 1
        assert len(fake.complete_calls) == 0

    def test_no_egress_guards_true_streaming(self) -> None:
        """No egress guards → TRUE_STREAMING; streaming path is used."""
        client, fake = _make_streaming_client()
        resp = client.post(
            "/v1/chat/completions",
            json={"model": "default", "messages": [{"role": "user", "content": "hi"}], "stream": True},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        assert len(fake.stream_calls) == 1


# ---------------------------------------------------------------------------
# TestBufferedStreamingRoute
# ---------------------------------------------------------------------------


class TestBufferedStreamingRoute:
    """A route with a non-incremental egress guard buffers but still emits SSE."""

    def test_returns_sse_content_type(self) -> None:
        regex = RegexGuard(patterns=["forbidden"], reason="blocked")
        guards: list[Guardrail] = [regex]
        client, _ = _make_streaming_client(egress_guards=guards)
        resp = client.post(
            "/v1/chat/completions",
            json={"model": "default", "messages": [{"role": "user", "content": "hi"}], "stream": True},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

    def test_valid_openai_sse_frames(self) -> None:
        regex = RegexGuard(patterns=["forbidden"], reason="blocked")
        guards: list[Guardrail] = [regex]
        client, _ = _make_streaming_client(egress_guards=guards)
        resp = client.post(
            "/v1/chat/completions",
            json={"model": "default", "messages": [{"role": "user", "content": "hi"}], "stream": True},
        )
        frames = _parse_sse(resp.text)
        data_frames = [f for f in frames if not f.get("_done")]
        assert len(data_frames) >= 1
        frame = data_frames[0]
        assert frame["object"] == "chat.completion.chunk"
        assert "choices" in frame

    def test_ends_with_done(self) -> None:
        regex = RegexGuard(patterns=["forbidden"], reason="blocked")
        guards: list[Guardrail] = [regex]
        client, _ = _make_streaming_client(egress_guards=guards)
        resp = client.post(
            "/v1/chat/completions",
            json={"model": "default", "messages": [{"role": "user", "content": "hi"}], "stream": True},
        )
        frames = _parse_sse(resp.text)
        assert frames[-1] == {"_done": True}

    def test_uses_complete_not_stream(self) -> None:
        """Buffered route calls provider.complete(), not provider.stream()."""
        regex = RegexGuard(patterns=["forbidden"], reason="blocked")
        guards: list[Guardrail] = [regex]
        client, fake = _make_streaming_client(
            egress_guards=guards,
        )
        # Override complete_response for assertion
        fake.complete_response = "safe response"
        client.post(
            "/v1/chat/completions",
            json={"model": "default", "messages": [{"role": "user", "content": "hi"}], "stream": True},
        )
        assert len(fake.complete_calls) == 1
        assert len(fake.stream_calls) == 0

    def test_content_in_buffered_frame(self) -> None:
        regex = RegexGuard(patterns=["forbidden"], reason="blocked")
        guards: list[Guardrail] = [regex]
        fake = FakeProvider(complete_response="safe response")
        executor = PipelineExecutor()
        egress_node = GuardNode(guards, name="egress")
        executor.register("default", provider=fake, egress=[egress_node])
        app = create_app(executor, no_auth=True)
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post(
            "/v1/chat/completions",
            json={"model": "default", "messages": [{"role": "user", "content": "hi"}], "stream": True},
        )
        frames = _parse_sse(resp.text)
        data_frames = [f for f in frames if not f.get("_done")]
        content = data_frames[0]["choices"][0]["delta"].get("content", "")
        assert content == "safe response"


# ---------------------------------------------------------------------------
# TestLateViolationStream
# ---------------------------------------------------------------------------


class TestLateViolationStream:
    """A finalize() block triggers a late-violation event."""

    def test_late_violation_emits_content_filter_finish(self) -> None:
        guards: list[Guardrail] = [_LateViolationGuard()]
        client, _ = _make_streaming_client(egress_guards=guards)
        resp = client.post(
            "/v1/chat/completions",
            json={"model": "default", "messages": [{"role": "user", "content": "hi"}], "stream": True},
        )
        frames = _parse_sse(resp.text)
        data_frames = [f for f in frames if not f.get("_done")]
        finish_reasons = [
            f["choices"][0]["finish_reason"]
            for f in data_frames
            if f.get("choices")
        ]
        assert "content_filter" in finish_reasons

    def test_late_violation_has_aegis_event(self) -> None:
        guards: list[Guardrail] = [_LateViolationGuard()]
        client, _ = _make_streaming_client(egress_guards=guards)
        resp = client.post(
            "/v1/chat/completions",
            json={"model": "default", "messages": [{"role": "user", "content": "hi"}], "stream": True},
        )
        frames = _parse_sse(resp.text)
        aegis_events = [f.get("aegis_event") for f in frames if f.get("aegis_event")]
        assert "late_violation" in aegis_events

    def test_late_violation_ends_with_done(self) -> None:
        guards: list[Guardrail] = [_LateViolationGuard()]
        client, _ = _make_streaming_client(egress_guards=guards)
        resp = client.post(
            "/v1/chat/completions",
            json={"model": "default", "messages": [{"role": "user", "content": "hi"}], "stream": True},
        )
        frames = _parse_sse(resp.text)
        assert frames[-1] == {"_done": True}

    def test_chunk_violation_emits_stream_violation(self) -> None:
        """A mid-stream chunk block emits stream_violation event."""
        chunk_blocker = _ChunkBlockGuard(forbidden="from")
        guards: list[Guardrail] = [chunk_blocker]
        client, _ = _make_streaming_client(
            egress_guards=guards,
            stream_chunks=["hello", " from", " fake"],
        )
        resp = client.post(
            "/v1/chat/completions",
            json={"model": "default", "messages": [{"role": "user", "content": "hi"}], "stream": True},
        )
        frames = _parse_sse(resp.text)
        aegis_events = [f.get("aegis_event") for f in frames if f.get("aegis_event")]
        assert "stream_violation" in aegis_events


# ---------------------------------------------------------------------------
# TestNonStreamingStillWorks
# ---------------------------------------------------------------------------


class TestNonStreamingStillWorks:
    """Verify stream=false still returns JSON (not SSE)."""

    def test_non_streaming_returns_json(self) -> None:
        client, _ = _make_streaming_client(
            egress_guards=[_AllowIncrementalGuard()],
        )
        resp = client.post(
            "/v1/chat/completions",
            json={"model": "default", "messages": [{"role": "user", "content": "hi"}], "stream": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "chat.completion"
        assert "choices" in data
        assert "usage" in data


# ---------------------------------------------------------------------------
# TestStreamDowngradeLint
# ---------------------------------------------------------------------------


class TestStreamDowngradeLint:
    """lint_policy reports AEG-POL-003 when egress guard causes streaming downgrade."""

    def _write_config(self, tmp_path: Path, content: str) -> Path:
        p = tmp_path / "aegis.yaml"
        p.write_text(textwrap.dedent(content))
        return p

    def test_non_incremental_egress_reports_pol003(self, tmp_path: Path) -> None:
        from aegis_cli.commands.policy import lint_policy

        cfg = self._write_config(tmp_path, """
            guardrails:
              regex_guard:
                pack: aegis_core
                streaming: none
            routes:
              my_route:
                pipeline:
                  egress: [regex_guard]
        """)
        issues = lint_policy(cfg)
        codes = [i.code for i in issues]
        assert "AEG-POL-003" in codes

    def test_incremental_egress_no_pol003(self, tmp_path: Path) -> None:
        from aegis_cli.commands.policy import lint_policy

        cfg = self._write_config(tmp_path, """
            guardrails:
              inc_guard:
                pack: aegis_core
                streaming: incremental
            routes:
              my_route:
                pipeline:
                  egress: [inc_guard]
        """)
        issues = lint_policy(cfg)
        pol003 = [i for i in issues if i.code == "AEG-POL-003"]
        assert not pol003

    def test_global_pipeline_egress_downgrade(self, tmp_path: Path) -> None:
        from aegis_cli.commands.policy import lint_policy

        cfg = self._write_config(tmp_path, """
            guardrails:
              regex_guard:
                pack: aegis_core
                streaming: none
            pipeline:
              egress: [regex_guard]
        """)
        issues = lint_policy(cfg)
        codes = [i.code for i in issues]
        assert "AEG-POL-003" in codes

    def test_pol003_message_names_guard(self, tmp_path: Path) -> None:
        from aegis_cli.commands.policy import lint_policy

        cfg = self._write_config(tmp_path, """
            guardrails:
              my_regex:
                pack: aegis_core
                streaming: none
            routes:
              r:
                pipeline:
                  egress: [my_regex]
        """)
        issues = lint_policy(cfg)
        pol003 = [i for i in issues if i.code == "AEG-POL-003"]
        assert any("my_regex" in i.message for i in pol003)
