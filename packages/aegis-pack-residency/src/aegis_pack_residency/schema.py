"""ResidencyProfile — declared residency metadata for a provider endpoint."""

from __future__ import annotations

from pydantic import BaseModel, field_validator


class ResidencyProfile(BaseModel):
    """Declared residency metadata for a provider endpoint.

    Attributes:
        region: Canonical region identifier (e.g. ``"eu-west-1"``).
        jurisdiction: Legal jurisdiction (e.g. ``"EU"``, ``"US"``).
        endpoint_url: The provider API endpoint URL whose embedded region
            will be validated against *region* by the lint validator.
        source_url: Human-readable reference (spec, DPA, etc.) — optional.
    """

    region: str
    jurisdiction: str
    endpoint_url: str = ""
    source_url: str = ""

    @field_validator("region")
    @classmethod
    def region_nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("region must not be empty")
        return v.strip()

    @field_validator("jurisdiction")
    @classmethod
    def jurisdiction_nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("jurisdiction must not be empty")
        return v.strip()
