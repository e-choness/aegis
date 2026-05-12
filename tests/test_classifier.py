import pytest
from src.aegis.services.classifier import DataClassifier
from src.aegis.models import DataClassification


@pytest.fixture
def clf():
    return DataClassifier()


def test_canadian_sin_is_restricted(clf):
    assert clf.classify("Customer SIN: 123-456-789") == DataClassification.RESTRICTED


def test_credit_card_is_restricted(clf):
    assert clf.classify("card number: 4111 1111 1111 1111") == DataClassification.RESTRICTED


def test_account_keyword_is_restricted(clf):
    assert clf.classify("please look up account_number 987654321") == DataClassification.RESTRICTED


def test_bearer_token_is_confidential(clf):
    assert clf.classify("Authorization: Bearer eyJhbGciOi...") == DataClassification.CONFIDENTIAL


def test_api_key_keyword_is_confidential(clf):
    assert clf.classify("set the api_key for this service") == DataClassification.CONFIDENTIAL


def test_plain_code_is_internal(clf):
    assert clf.classify("def calculate_sum(a, b): return a + b") == DataClassification.INTERNAL


def test_restricted_takes_priority_over_confidential(clf):
    text = "api_key and SIN 123 456 789 present"
    assert clf.classify(text) == DataClassification.RESTRICTED


def test_empty_string_is_internal(clf):
    assert clf.classify("") == DataClassification.INTERNAL
