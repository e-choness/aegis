import pytest
from src.gateway.services.router import ModelRouter
from src.gateway.services.health import AlwaysHealthyChecker
from src.gateway.models import DataClassification


@pytest.fixture
def router():
    return ModelRouter(health_checker=AlwaysHealthyChecker())


def test_restricted_routing_invariant(router):
    """RESTRICTED data must NEVER reach tier 1 providers."""
    config = router.route("any_task", "any", DataClassification.RESTRICTED)
    assert config.tier >= 2, f"Tier {config.tier} violates RESTRICTED invariant"
    assert config.provider not in ("anthropic", "azure_openai")


def test_restricted_routing_invariant_high_complexity(router):
    config = router.route("security_audit", "high", DataClassification.RESTRICTED)
    assert config.tier >= 2
    assert config.provider not in ("anthropic", "azure_openai")


def test_commit_summary_uses_haiku(router):
    config = router.route("commit_summary", "low", DataClassification.INTERNAL)
    assert config.alias == "haiku"


def test_pr_review_uses_sonnet(router):
    config = router.route("pr_review", "medium", DataClassification.INTERNAL)
    assert config.alias == "sonnet"


def test_security_audit_uses_opus(router):
    config = router.route("security_audit", "high", DataClassification.INTERNAL)
    assert config.alias == "opus"


def test_budget_degradation_opus_to_sonnet(router):
    config = router.route("security_audit", "high", DataClassification.INTERNAL, budget_remaining_usd=0.50)
    assert config.alias == "sonnet"


def test_unknown_task_defaults_to_sonnet(router):
    config = router.route("some_future_task", "medium", DataClassification.INTERNAL)
    assert config.alias == "sonnet"


def test_model_id_is_set(router):
    config = router.route("pr_review", "medium", DataClassification.INTERNAL)
    assert config.model_id, "model_id must not be empty"


def test_cost_fields_present(router):
    config = router.route("haiku", "low", DataClassification.INTERNAL)
    assert config.cost_input_per_mtok >= 0
    assert config.cost_output_per_mtok >= 0
