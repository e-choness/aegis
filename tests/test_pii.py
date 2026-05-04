import pytest
from src.gateway.services.pii import PIIMasker


@pytest.fixture(scope="module")
def masker():
    return PIIMasker()


def test_canadian_sin_dashes_masked(masker):
    masked, restore_map = masker.mask("Customer SIN: 123-456-789 on file")
    assert "123-456-789" not in masked
    assert restore_map, "Expected restore_map to be non-empty"


def test_canadian_sin_spaces_masked(masker):
    masked, restore_map = masker.mask("SIN 987 654 321 found")
    assert "987 654 321" not in masked
    assert restore_map


def test_credit_card_masked(masker):
    masked, restore_map = masker.mask("Card: 4111 1111 1111 1111 approved")
    assert "4111 1111 1111 1111" not in masked
    assert restore_map


def test_clean_text_unchanged(masker):
    text = "def calculate_tax(income: float) -> float: return income * 0.15"
    masked, restore_map = masker.mask(text)
    assert masked == text
    assert not restore_map


def test_empty_string(masker):
    masked, restore_map = masker.mask("")
    assert masked == ""
    assert not restore_map


def test_unmask_restores_original(masker):
    original = "SIN: 123-456-789 — please process"
    masked, restore_map = masker.mask(original)
    assert masked != original
    restored = masker.unmask(masked, restore_map)
    assert "123-456-789" in restored


def test_unmask_noop_on_empty_map(masker):
    text = "hello world"
    assert masker.unmask(text, {}) == text


def test_multiple_entities_all_masked(masker):
    text = "SIN 123-456-789 and card 4111-1111-1111-1111 in the same prompt"
    masked, restore_map = masker.mask(text)
    assert "123-456-789" not in masked
    assert len(restore_map) >= 2


def test_scan_output_detects_leaked_sin(masker):
    leaked = masker.scan_output("The customer SIN is 123-456-789")
    assert len(leaked) > 0


def test_scan_output_clean_text_empty(masker):
    leaked = masker.scan_output("No sensitive data here at all.")
    assert leaked == []
