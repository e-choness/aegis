"""Tests for eval framework: scorer, runner, and golden dataset integrity."""
from __future__ import annotations
import pytest
from evals.scorer import score_case, EvalResult, CaseScore, ReviewOutput
from evals.runner import run_eval, extract_flags_from_review
from evals.golden_dataset import GOLDEN_CASES, REQUIRED_CATEGORIES, EvalCase


# ── scorer unit tests ─────────────────────────────────────────────────────────

def test_perfect_match():
    score = score_case("x", ["sql_injection"], ["sql_injection"])
    assert score.precision == 1.0
    assert score.recall == 1.0
    assert score.f1 == 1.0
    assert not score.false_positive
    assert not score.false_negative


def test_false_positive():
    score = score_case("x", [], ["sql_injection"])
    assert score.precision == 0.0
    # recall is 0.0 when expected is empty but actual is non-empty (shouldn't have flagged anything)
    assert score.recall == 0.0
    assert score.false_positive is True
    assert score.false_negative is False


def test_false_negative():
    score = score_case("x", ["sql_injection"], [])
    assert score.recall == 0.0
    assert score.false_negative is True
    assert score.false_positive is False


def test_partial_match():
    score = score_case("x", ["sql_injection", "missing_auth"], ["sql_injection"])
    assert score.precision == 1.0
    assert score.recall == 0.5
    assert score.f1 == pytest.approx(2 * 1.0 * 0.5 / 1.5, rel=1e-6)


def test_empty_expected_empty_actual():
    score = score_case("fp", [], [])
    assert score.precision == 1.0
    assert score.recall == 1.0
    assert score.f1 == 1.0
    assert not score.false_positive
    assert not score.false_negative


def test_f1_harmonic_mean():
    score = score_case("x", ["a", "b", "c"], ["a", "b"])
    assert score.precision == 1.0
    assert score.recall == pytest.approx(2 / 3, rel=1e-6)
    assert score.f1 == pytest.approx(2 * 1.0 * (2 / 3) / (1.0 + 2 / 3), rel=1e-6)


# ── EvalResult aggregation ────────────────────────────────────────────────────

def test_eval_result_f1_aggregation():
    cases = [
        CaseScore("a", precision=1.0, recall=1.0, f1=1.0, false_positive=False, false_negative=False),
        CaseScore("b", precision=0.5, recall=0.5, f1=0.5, false_positive=False, false_negative=True),
    ]
    result = EvalResult(model_alias="test-model", case_scores=cases)
    assert result.mean_precision == pytest.approx(0.75, rel=1e-6)
    assert result.mean_recall == pytest.approx(0.75, rel=1e-6)
    assert result.false_positive_rate == 0.0


def test_eval_result_false_positive_rate():
    cases = [
        CaseScore("a", 0.0, 1.0, 0.0, false_positive=True, false_negative=False),
        CaseScore("b", 1.0, 1.0, 1.0, false_positive=False, false_negative=False),
    ]
    result = EvalResult(model_alias="test", case_scores=cases)
    assert result.false_positive_rate == 0.5


def test_beats_baseline():
    baseline_cases = [CaseScore("x", 0.8, 0.8, 0.8, False, False)]
    baseline = EvalResult("baseline", baseline_cases)

    better_cases = [CaseScore("x", 0.9, 0.9, 0.9, False, False)]
    better = EvalResult("new", better_cases)

    # 0.9 vs 0.8 * 1.05 = 0.84 — better passes
    assert better.beats_baseline(baseline)

    # Barely over baseline (< 5%)
    marginal_cases = [CaseScore("x", 0.83, 0.83, 0.83, False, False)]
    marginal = EvalResult("marginal", marginal_cases)
    assert not marginal.beats_baseline(baseline)


# ── flag extractor ────────────────────────────────────────────────────────────

def test_extract_sql_injection():
    flags = extract_flags_from_review("Found SQL injection in line 42")
    assert "sql_injection" in flags


def test_extract_n_plus_1():
    flags = extract_flags_from_review("This causes an N+1 query problem")
    assert "n_plus_1_query" in flags


def test_extract_ssrf():
    flags = extract_flags_from_review("Potential SSRF vulnerability detected")
    assert "ssrf" in flags


def test_extract_hardcoded_secret():
    flags = extract_flags_from_review("hardcoded secret in config file")
    assert "hardcoded_secret" in flags


def test_extract_missing_auth():
    flags = extract_flags_from_review("missing auth check before accessing resource")
    assert "missing_auth" in flags


def test_extract_no_flags():
    flags = extract_flags_from_review("Code looks good, no issues found.")
    assert flags == []


def test_extract_flags_deduplicates():
    flags = extract_flags_from_review("SQL injection here. SQL injection there too.")
    assert flags.count("sql_injection") == 1


# ── golden dataset integrity ──────────────────────────────────────────────────

def test_golden_dataset_has_required_categories():
    categories = {c.category for c in GOLDEN_CASES}
    assert REQUIRED_CATEGORIES.issubset(categories), (
        f"Missing categories: {REQUIRED_CATEGORIES - categories}"
    )


def test_golden_dataset_no_duplicate_ids():
    ids = [c.id for c in GOLDEN_CASES]
    assert len(ids) == len(set(ids)), "Duplicate IDs in golden dataset"


def test_golden_dataset_all_cases_have_description():
    for case in GOLDEN_CASES:
        assert case.description, f"Case {case.id} has no description"


def test_golden_dataset_false_positives_have_empty_flags():
    fp_cases = [c for c in GOLDEN_CASES if c.category == "false_positive"]
    for case in fp_cases:
        assert case.expected_flags == [], (
            f"False positive case {case.id} should have empty flags"
        )


def test_golden_dataset_security_cases_have_flags():
    sec_cases = [c for c in GOLDEN_CASES if c.category == "security"]
    for case in sec_cases:
        assert len(case.expected_flags) > 0, (
            f"Security case {case.id} should have at least one flag"
        )


# ── runner integration (async, injectable review_fn) ─────────────────────────

@pytest.mark.asyncio
async def test_run_eval_perfect_model():
    """A model that always returns exactly the expected flags gets F1=1.0."""
    async def perfect_review_fn(diff: str, model_alias: str) -> ReviewOutput:
        # Find matching case by diff content to return correct flags
        for case in GOLDEN_CASES:
            if case.diff.strip() in diff.strip() or diff.strip() in case.diff.strip():
                return ReviewOutput(flags=case.expected_flags)
        return ReviewOutput(flags=[])

    cases = [
        EvalCase("t1", "security", "diff text", ["sql_injection"], "critical", "test"),
    ]

    async def exact_fn(diff: str, model_alias: str) -> ReviewOutput:
        return ReviewOutput(flags=["sql_injection"])

    result = await run_eval("test-model", exact_fn, cases=cases)
    assert result.f1 == 1.0
    assert result.mean_precision == 1.0
    assert result.mean_recall == 1.0


@pytest.mark.asyncio
async def test_run_eval_model_with_false_positive():
    async def fp_fn(diff: str, model_alias: str) -> ReviewOutput:
        return ReviewOutput(flags=["sql_injection"])  # wrong — case expects []

    cases = [EvalCase("fp1", "false_positive", "clean diff", [], "none", "test")]
    result = await run_eval("test-model", fp_fn, cases=cases)
    assert result.false_positive_rate == 1.0


@pytest.mark.asyncio
async def test_run_eval_handles_review_fn_exception():
    async def failing_fn(diff: str, model_alias: str) -> ReviewOutput:
        raise RuntimeError("provider error")

    cases = [EvalCase("err1", "security", "diff", ["sql_injection"], "critical", "test")]
    result = await run_eval("test-model", failing_fn, cases=cases)
    assert result.f1 == 0.0
    assert result.case_scores[0].recall == 0.0


@pytest.mark.asyncio
async def test_run_eval_uses_golden_cases_by_default():
    call_count = 0

    async def counting_fn(diff: str, model_alias: str) -> ReviewOutput:
        nonlocal call_count
        call_count += 1
        return ReviewOutput(flags=[])

    await run_eval("test", counting_fn)
    assert call_count == len(GOLDEN_CASES)
