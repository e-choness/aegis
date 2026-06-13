"""Aegis residency policy pack — declared-metadata schema, lint, and fail-closed guard."""

from aegis_pack_residency.guard import ResidencyGuard
from aegis_pack_residency.lint import LintViolation, lint_endpoint
from aegis_pack_residency.schema import ResidencyProfile

__all__ = ["LintViolation", "ResidencyGuard", "ResidencyProfile", "lint_endpoint"]
