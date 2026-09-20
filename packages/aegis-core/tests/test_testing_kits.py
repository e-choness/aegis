"""Tests for the NodeContractKit and ExporterContractKit (Phase 3 plugin author path)."""

from __future__ import annotations

import pytest

from aegis_core.pipeline.state import RunState, RunStateDelta
from aegis_core.testing.exporters import ExporterContractKit
from aegis_core.testing.nodes import NodeContractKit


class _StubNode:
    name = "stub-node"

    async def run(self, state: RunState) -> RunStateDelta:
        return RunStateDelta()


class _MissingNameNode:
    async def run(self, state: RunState) -> RunStateDelta:
        return RunStateDelta()


class _StubExporter:
    name = "stub-exporter"

    async def export(self, records: list[dict]) -> None:
        return None


# ---------------------------------------------------------------------------
# NodeContractKit
# ---------------------------------------------------------------------------


class TestNodeContractKit:
    def test_assert_isinstance_passes(self) -> None:
        NodeContractKit(_StubNode()).assert_isinstance()

    def test_assert_isinstance_fails_without_name(self) -> None:
        with pytest.raises(AssertionError):
            NodeContractKit(_MissingNameNode()).assert_isinstance()

    def test_assert_name(self) -> None:
        NodeContractKit(_StubNode()).assert_name()

    @pytest.mark.asyncio
    async def test_assert_run_returns_delta(self) -> None:
        await NodeContractKit(_StubNode()).assert_run_returns_delta()

    @pytest.mark.asyncio
    async def test_assert_all_async(self) -> None:
        await NodeContractKit(_StubNode()).assert_all_async()


# ---------------------------------------------------------------------------
# ExporterContractKit
# ---------------------------------------------------------------------------


class TestExporterContractKit:
    def test_assert_isinstance_passes(self) -> None:
        ExporterContractKit(_StubExporter()).assert_isinstance()

    def test_assert_name(self) -> None:
        ExporterContractKit(_StubExporter()).assert_name()

    @pytest.mark.asyncio
    async def test_assert_export_accepts_empty_list(self) -> None:
        await ExporterContractKit(_StubExporter()).assert_export_accepts_empty_list()

    @pytest.mark.asyncio
    async def test_assert_all_async(self) -> None:
        await ExporterContractKit(_StubExporter()).assert_all_async()
