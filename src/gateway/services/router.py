from __future__ import annotations
import yaml
from pathlib import Path
from ..models import DataClassification, ModelConfig


_REGISTRY_PATH = Path(__file__).parent.parent.parent.parent / "config" / "model_registry.yaml"

def _load_registry() -> dict:
    with open(_REGISTRY_PATH) as f:
        return yaml.safe_load(f)


class ModelRouter:
    """
    Maps task type + complexity + data classification + budget → ModelConfig.
    Rules-based (not ML) so routing is deterministic, auditable, and testable.
    RESTRICTED data routing to cloud is a hard code invariant, never overridable.
    """

    TASK_ALIAS_MAP: dict[str, str] = {
        "commit_summary":       "haiku",
        "simple_qa":            "haiku",
        "routing":              "haiku",
        "classification":       "haiku",
        "pr_review":            "sonnet",
        "rag_response":         "sonnet",
        "code_explanation":     "sonnet",
        "documentation":        "sonnet",
        "deployment_check":     "sonnet",
        "security_audit":       "opus",
        "architecture_review":  "opus",
        "multi_file_refactor":  "opus",
    }

    FALLBACK_CHAIN: list[tuple[str, str, int]] = [
        ("anthropic",   "tier1_anthropic", 1),
        ("azure_openai","tier1_azure",     1),
        ("vllm",        "tier2_vllm",      2),
        ("ollama",      "tier3_ollama",    3),
    ]

    def __init__(self, health_checker=None) -> None:
        self._registry = _load_registry()
        self._health_checker = health_checker

    def route(
        self,
        task_type: str,
        complexity: str = "medium",
        data_classification: str = DataClassification.INTERNAL,
        budget_remaining_usd: float = float("inf"),
    ) -> ModelConfig:
        # RULE 1 — RESTRICTED data never reaches cloud (hard invariant)
        if data_classification == DataClassification.RESTRICTED:
            return self._build_config("local", "vllm", "tier2_vllm", 2)

        alias = self.TASK_ALIAS_MAP.get(task_type, "sonnet")

        # RULE 3 — Escalate to opus for high-complexity security work
        if complexity == "high" and task_type == "security_audit":
            alias = "opus"

        # RULE 4 — Budget-aware degradation
        if alias == "opus" and budget_remaining_usd < 1.00:
            alias = "sonnet"

        return self._select_available_tier(alias)

    def _select_available_tier(self, alias: str) -> ModelConfig:
        for provider_name, registry_key, tier in self.FALLBACK_CHAIN:
            if self._is_healthy(provider_name):
                return self._build_config(alias, provider_name, registry_key, tier)
        # Ollama is always the final fallback (offline, no network required)
        return self._build_config(alias, "ollama", "tier3_ollama", 3)

    def _is_healthy(self, provider: str) -> bool:
        if self._health_checker is None:
            return provider == "anthropic"
        return self._health_checker.is_healthy(provider)

    def _build_config(self, alias: str, provider: str, registry_key: str, tier: int) -> ModelConfig:
        entry = self._registry.get(alias, self._registry["sonnet"])
        model_id = entry.get(registry_key, entry.get("tier3_ollama", "qwen2.5:7b"))
        margin = float(entry.get("tokenizer_margin", 1.0))
        return ModelConfig(
            alias=alias,
            provider=provider,
            tier=tier,
            model_id=model_id,
            cost_input_per_mtok=float(entry.get("cost_input_per_mtok", 0.0)),
            cost_output_per_mtok=float(entry.get("cost_output_per_mtok", 0.0)),
            tokenizer_margin=margin,
        )
