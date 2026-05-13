"""Factory for creating and managing LangServe-compatible Runnables.

A Runnable in LangServe is a chainable component with:
- Input schema (Pydantic model JSON schema)
- Output schema
- Invocable logic (invoke, batch, stream)
- Metadata (description, tags)
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Protocol
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class InferenceInput(BaseModel):
    """Input schema for the 'inference' Runnable."""
    prompt: str = Field(..., description="The prompt text to send to the LLM")
    task_type: str = Field(default="general", description="Task type for routing (commit_summary, pr_review, security_audit, etc.)")
    team_id: str = Field(..., description="Team identifier for budget tracking")
    user_id: str = Field(..., description="User identifier for audit trail")
    complexity: str = Field(default="medium", description="Complexity level: low, medium, high")
    trace_id: Optional[str] = Field(None, description="Optional trace ID for correlation")


class InferenceOutput(BaseModel):
    """Output schema for the 'inference' Runnable."""
    output: Optional[str] = Field(None, description="The LLM response text")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Response metadata (model, cost, latency, etc.)")


class RunnableMetadata(BaseModel):
    """Metadata for a registered Runnable."""
    name: str
    description: str
    tags: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    config_schema: Optional[dict[str, Any]] = None


class RunnableFactory:
    """Factory for creating and managing Runnables."""
    
    def __init__(self):
        """Initialize the factory with built-in Runnables."""
        self._runnables: dict[str, RunnableMetadata] = {}
        self._register_builtin_runnables()
    
    def _register_builtin_runnables(self) -> None:
        """Register all built-in Runnables."""
        # Inference Runnable
        self._register_runnable(
            name="inference",
            description="Execute an AI inference request with data classification, PII masking, and cost routing",
            tags=["inference", "classification", "pii_masking", "budget"],
            input_schema=InferenceInput,
            output_schema=InferenceOutput,
        )
    
    def _register_runnable(
        self,
        name: str,
        description: str,
        tags: list[str],
        input_schema: type[BaseModel],
        output_schema: type[BaseModel],
        config_schema: Optional[dict[str, Any]] = None,
    ) -> None:
        """Register a Runnable with its schemas.
        
        Args:
            name: Runnable identifier (must be unique)
            description: Human-readable description
            tags: List of tags for categorization
            input_schema: Pydantic model class for inputs
            output_schema: Pydantic model class for outputs
            config_schema: Optional JSON schema for config (invoke config)
        """
        # Generate JSON schemas from Pydantic models
        input_json_schema = input_schema.model_json_schema()
        output_json_schema = output_schema.model_json_schema()
        
        metadata = RunnableMetadata(
            name=name,
            description=description,
            tags=tags,
            input_schema=input_json_schema,
            output_schema=output_json_schema,
            config_schema=config_schema,
        )
        
        self._runnables[name] = metadata
        logger.info(f"Registered Runnable: {name} with tags {tags}")
    
    def list_runnables(self) -> list[dict[str, Any]]:
        """List all registered Runnables with metadata.
        
        Returns:
            List of Runnable metadata dicts
        """
        return [r.model_dump() for r in self._runnables.values()]
    
    def get_schema(self, name: str) -> Optional[dict[str, Any]]:
        """Get the schema for a Runnable by name.
        
        Args:
            name: Runnable name
        
        Returns:
            Runnable metadata dict, or None if not found
        """
        if name not in self._runnables:
            return None
        
        metadata = self._runnables[name]
        return metadata.model_dump()
    
    def register_custom_runnable(
        self,
        name: str,
        description: str,
        tags: list[str],
        input_schema: dict[str, Any],
        output_schema: dict[str, Any],
    ) -> None:
        """Register a custom Runnable (for extensions).
        
        Args:
            name: Unique Runnable identifier
            description: Human-readable description
            tags: Categorization tags
            input_schema: JSON schema for inputs
            output_schema: JSON schema for outputs
        """
        metadata = RunnableMetadata(
            name=name,
            description=description,
            tags=tags,
            input_schema=input_schema,
            output_schema=output_schema,
        )
        
        self._runnables[name] = metadata
        logger.info(f"Registered custom Runnable: {name}")
    
    def has_runnable(self, name: str) -> bool:
        """Check if a Runnable is registered.
        
        Args:
            name: Runnable name
        
        Returns:
            True if Runnable exists
        """
        return name in self._runnables
