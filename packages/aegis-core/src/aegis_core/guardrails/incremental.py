"""IncrementalGuardrail — Protocol for guardrails that support streaming inspection."""

from __future__ import annotations

from typing import ClassVar, Literal, Protocol, runtime_checkable

from aegis_core.guardrails.protocol import Guardrail
from aegis_core.pipeline.verdict import Verdict


@runtime_checkable
class IncrementalGuardrail(Guardrail, Protocol):
    """A guardrail that can inspect content chunk by chunk during streaming.

    When a compiled pipeline route has only incremental egress guards,
    the server can true-stream: each chunk from the provider is scanned
    via :meth:`scan_chunk` before being forwarded to the client.  After
    the last chunk :meth:`finalize` runs a final pass; a block there
    triggers a late-violation event.

    Implementors must also satisfy the base :class:`~aegis_core.guardrails.protocol.Guardrail`
    contract (``name``, ``scan``).
    """

    streaming: ClassVar[Literal["none", "incremental"]]

    async def scan_chunk(self, chunk: str) -> Verdict:
        """Scan a single streaming chunk.

        Called for every token/delta emitted by the provider.
        Return :meth:`~aegis_core.pipeline.verdict.Verdict.block` to
        immediately stop the stream.
        """
        ...

    async def finalize(self, accumulated: str) -> Verdict:
        """Final pass over the complete accumulated response text.

        Called once after all chunks have been received.  A block here
        triggers a late-violation event; the stream is truncated and the
        client receives a ``content_filter`` finish reason instead of
        ``stop``.
        """
        ...
