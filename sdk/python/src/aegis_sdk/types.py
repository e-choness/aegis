from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class InferenceRequest:
    prompt: str
    task_type: str = "general"
    team_id: str = ""
    user_id: str = ""
    trace_id: Optional[str] = None
    model_alias: Optional[str] = None
    max_tokens: int = 2048


@dataclass
class JobResult:
    job_id: str
    status: str          # pending | running | completed | failed
    result: Optional[str] = None
    error: Optional[str] = None
    model_used: Optional[str] = None
    cost_usd: Optional[float] = None


@dataclass
class PollOptions:
    timeout: float = 90.0       # seconds
    poll_interval: float = 2.0  # seconds


@dataclass
class ReviewPROptions:
    diff_url: str
    team_id: str
    user_id: str
    trace_id: Optional[str] = None
