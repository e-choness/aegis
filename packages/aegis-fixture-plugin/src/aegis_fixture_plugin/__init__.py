"""Fixture plugin package — used only in Aegis registry tests."""

from __future__ import annotations


class FixtureProvider:
    """Minimal stub that satisfies the ModelProvider contract in tests."""

    name: str = "fixture-provider"


class FixtureGuardrail:
    """Minimal stub that satisfies the Guardrail contract in tests."""

    name: str = "fixture-guardrail"
