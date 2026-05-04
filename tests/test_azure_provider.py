import pytest
from src.gateway.providers.azure_openai_provider import AzureOpenAIProvider, OPUS_TOKENIZER_MARGIN


def _provider():
    p = object.__new__(AzureOpenAIProvider)
    return p


def test_opus_cost_includes_tokenizer_margin():
    p = _provider()
    cost = p.estimate_cost_usd(1_000_000, 200_000, "opus")
    # (1M*$5 + 200K*$25) / 1M * 1.35 = $13.50
    assert abs(cost - 13.50) < 0.01


def test_sonnet_cost_no_margin():
    p = _provider()
    cost = p.estimate_cost_usd(1_000_000, 200_000, "sonnet")
    # (1M*$3 + 200K*$15) / 1M = $6.00
    assert abs(cost - 6.00) < 0.01


def test_haiku_cost_no_margin():
    p = _provider()
    cost = p.estimate_cost_usd(1_000_000, 200_000, "haiku")
    assert abs(cost - 2.00) < 0.01


def test_tokenizer_margin_constant():
    assert OPUS_TOKENIZER_MARGIN == 1.35


def test_requires_endpoint_and_key(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)
    with pytest.raises(ValueError, match="AZURE_OPENAI_ENDPOINT"):
        AzureOpenAIProvider()


def test_factory_raises_on_missing_env(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)
    from src.gateway.providers.factory import ProviderFactory
    with pytest.raises(ValueError):
        ProviderFactory.get("azure_openai")
