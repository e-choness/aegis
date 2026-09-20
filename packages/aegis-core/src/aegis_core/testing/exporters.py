"""ExporterContractKit — shipped with aegis-core for plug-in authors to verify their exporter."""

from __future__ import annotations

from aegis_core.exporters.protocol import Exporter


class ExporterContractKit:
    """Asserts the full Exporter contract against an exporter instance.

    Usage in pytest::

        kit = ExporterContractKit(MyExporter())
        kit.assert_all()

    Or individually::

        kit.assert_isinstance()
        kit.assert_name()
        asyncio.run(kit.assert_export_accepts_empty_list())
        asyncio.run(kit.assert_export_accepts_records())
    """

    def __init__(self, exporter: object) -> None:
        self._exporter = exporter

    # ------------------------------------------------------------------
    # Individual assertions
    # ------------------------------------------------------------------

    def assert_isinstance(self) -> None:
        """Exporter satisfies the Exporter runtime-checkable Protocol."""
        assert isinstance(self._exporter, Exporter), (
            f"{type(self._exporter).__name__} does not satisfy Exporter Protocol"
        )

    def assert_name(self) -> None:
        """Exporter has a non-empty string ``name`` attribute."""
        name = getattr(self._exporter, "name", None)
        assert isinstance(name, str), "Exporter.name must be a string"
        assert name, "Exporter.name must be non-empty"

    async def assert_export_accepts_empty_list(self) -> None:
        """export([]) does not raise."""
        await self._exporter.export([])  # type: ignore[union-attr]

    async def assert_export_accepts_records(self) -> None:
        """export() accepts a list of evidence-shaped dicts without raising."""
        records = [{"seq": 1, "prev_hash": "genesis", "hash": "sha256:test", "record_type": "test"}]
        await self._exporter.export(records)  # type: ignore[union-attr]

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def assert_all(self) -> None:
        """Run all synchronous contract assertions."""
        self.assert_isinstance()
        self.assert_name()

    async def assert_all_async(self) -> None:
        """Run all contract assertions including async ones."""
        self.assert_all()
        await self.assert_export_accepts_empty_list()
        await self.assert_export_accepts_records()
