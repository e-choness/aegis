"""Pydantic models for Aegis API request/response shapes."""

from __future__ import annotations

from pydantic import BaseModel


class RunCreateRequest(BaseModel):
    messages: list[dict[str, str]]
    route: str = "default"
    approvers: list[str] = []
    background: bool = False


class RunCreateResponse(BaseModel):
    run_id: str
    response: str | None
    principal_id: str
    events: list[dict[str, object]]
    status: str


class RunStatusResponse(BaseModel):
    run_id: str
    route: str
    principal_id: str
    status: str
    approvers: list[str]


class ResumeResponse(BaseModel):
    run_id: str
    status: str
    response: str | None
    events: list[dict[str, object]]
