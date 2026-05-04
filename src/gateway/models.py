from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class DataClassification(str, Enum):
    RESTRICTED = "RESTRICTED"
    CONFIDENTIAL = "CONFIDENTIAL"
    INTERNAL = "INTERNAL"
    PUBLIC = "PUBLIC"


class ProviderTier(int, Enum):
    TIER1_ANTHROPIC = 1
    TIER1_AZURE = 11
    TIER2_VLLM = 2
    TIER3_OLLAMA = 3


class ModelAlias(str, Enum):
    HAIKU = "haiku"
    SONNET = "sonnet"
    OPUS = "opus"
    LOCAL = "local"


class ModelConfig(BaseModel):
    alias: str
    provider: str
    tier: int
    model_id: str
    cost_input_per_mtok: float
    cost_output_per_mtok: float
    tokenizer_margin: float = 1.0


class InferenceRequest(BaseModel):
    prompt: str
    task_type: str = "general"
    team_id: str
    user_id: str
    complexity: str = "medium"
    trace_id: Optional[str] = None


class InferenceResponse(BaseModel):
    job_id: str
    status: str = "queued"
    trace_id: Optional[str] = None


class JobResult(BaseModel):
    job_id: str
    status: str
    content: Optional[str] = None
    model_alias: Optional[str] = None
    provider: Optional[str] = None
    tier: Optional[int] = None
    cost_usd: Optional[float] = None
    data_classification: Optional[str] = None
    error: Optional[str] = None


class AuditRecord(BaseModel):
    trace_id: str
    user_id: str
    team_id: str
    model_alias: str
    model_id: str
    provider: str
    tier: int
    data_classification: str
    cost_usd: float
    input_tokens: int = 0
    output_tokens: int = 0
    cache_hit: bool = False
    pii_detected: bool = False
    latency_ms: int = 0
