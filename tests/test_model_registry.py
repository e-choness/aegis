import yaml
import pytest
from pathlib import Path

REGISTRY_PATH = Path(__file__).parent.parent / "config" / "model_registry.yaml"

RETIRED_IDS = [
    "claude-3-haiku-20240307",
    "claude-3-5-sonnet-20240620",
    "claude-3-5-sonnet-20241022",
    "claude-3-opus-20240229",
    "claude-opus-4-20250514",
    "claude-sonnet-4-20250514",
]

ACTIVE_ALIASES = ["haiku", "sonnet", "opus"]


@pytest.fixture(scope="module")
def registry():
    with open(REGISTRY_PATH) as f:
        return yaml.safe_load(f)


def test_registry_file_exists():
    assert REGISTRY_PATH.exists(), "config/model_registry.yaml is missing"


def test_no_retired_model_ids(registry):
    registry_str = yaml.dump(registry)
    for retired in RETIRED_IDS:
        assert retired not in registry_str, f"Retired model ID found in registry: {retired}"


def test_active_aliases_present(registry):
    for alias in ACTIVE_ALIASES:
        assert alias in registry, f"Alias {alias!r} missing from registry"


def test_haiku_points_to_active_model(registry):
    assert registry["haiku"]["tier1_anthropic"] == "claude-haiku-4-5-20251001"


def test_sonnet_points_to_active_model(registry):
    assert registry["sonnet"]["tier1_anthropic"] == "claude-sonnet-4-6"


def test_opus_points_to_active_model(registry):
    assert registry["opus"]["tier1_anthropic"] == "claude-opus-4-7"


def test_opus_has_tokenizer_margin(registry):
    assert registry["opus"].get("tokenizer_margin") == 1.35


def test_all_aliases_have_ollama_fallback(registry):
    for alias in ACTIVE_ALIASES:
        assert "tier3_ollama" in registry[alias], f"{alias} missing tier3_ollama fallback"
