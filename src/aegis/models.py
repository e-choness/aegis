from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class DataClassification(str, Enum):
    RESTRICTED = "RESTRICTED"
    CONFIDENTIAL = "CONFIDENTIAL"
    INTERNAL = "INTERNAL"
    PUBLIC = "PUBLIC"


class ProviderTier(int, Enum):
    TIER1_ANTHROPIC = 1
    TIER1_AZURE = 11
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
    model: Optional[str] = None  # Model alias (haiku/sonnet/opus) or override
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


class WorkflowUsage(BaseModel):
    """Token usage and cost metrics for workflow execution."""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    tool_calls_count: int = 0
    model_calls_count: int = 0
    latency_ms: int = 0


class WorkflowInvokeRequest(BaseModel):
    """LangServe-compatible workflow invocation request."""
    input: Optional[dict[str, Any]] = None
    config: Optional[dict[str, Any]] = None


class WorkflowInvokeResponse(BaseModel):
    """LangServe-compatible workflow invocation response."""
    execution_id: str = ""
    workflow_id: str = ""
    status: str = "completed"
    output: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    usage: WorkflowUsage = Field(default_factory=WorkflowUsage)


class WorkflowBatchRequest(BaseModel):
    """Batch execution request for multiple inputs."""
    inputs: list[dict[str, Any]]
    config: Optional[dict[str, Any]] = None
    max_concurrency: int = Field(default=4, ge=1, le=16)


class WorkflowBatchResponse(BaseModel):
    """Batch execution response with results."""
    executions: list[WorkflowInvokeResponse]
