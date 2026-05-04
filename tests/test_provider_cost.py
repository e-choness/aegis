import pytest
from src.gateway.providers.anthropic_provider import AnthropicProvider, OPUS_TOKENIZER_MARGIN


def _provider():
    """Bypass __init__ to test cost calculation without an API key."""
    p = object.__new__(AnthropicProvider)
    return p


def test_opus_cost_estimate_applies_tokenizer_margin():
    p = _provider()
    cost = p.estimate_cost_usd(1_000_000, 200_000, "opus")
    # (1M * $5 + 200K * $25) / 1M * 1.35 = (5.00 + 5.00) * 1.35 = $13.50
    assert abs(cost - 13.50) < 0.01, f"Expected ~$13.50 but got ${cost:.4f}"


def test_sonnet_cost_no_margin():
    p = _provider()
    cost = p.estimate_cost_usd(1_000_000, 200_000, "sonnet")
    # (1M * $3 + 200K * $15) / 1M = 3.00 + 3.00 = $6.00
    assert abs(cost - 6.00) < 0.01


def test_haiku_cost_no_margin():
    p = _provider()
    cost = p.estimate_cost_usd(1_000_000, 200_000, "haiku")
    # (1M * $1 + 200K * $5) / 1M = 1.00 + 1.00 = $2.00
    assert abs(cost - 2.00) < 0.01


def test_opus_margin_constant():
    assert OPUS_TOKENIZER_MARGIN == 1.35
