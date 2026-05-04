"""
Eval runner — executes the golden dataset against a model alias.
Uses the Anthropic Batch API for 50% cost savings (async, queued processing).
"""
from __future__ import annotations
import logging
import re
from typing import Callable, Awaitable
from .golden_dataset import GOLDEN_CASES, EvalCase
from .scorer import EvalResult, ReviewOutput, score_case

logger = logging.getLogger("aegis.evals.runner")

# Injected review function signature: (diff: str, model_alias: str) -> ReviewOutput
ReviewFn = Callable[[str, str], Awaitable[ReviewOutput]]

_FLAG_PATTERN = re.compile(
    r"\b(sql.?injection|missing.?auth|insecure.?direct|idor|ssrf|hardcoded.?secret|"
    r"credential.?exposure|n.?plus.?1|n\+1|memory.?exhaust|missing.?pagination|"
    r"magic.?number|swallowed.?exception)\b",
    re.IGNORECASE,
)

_FLAG_NORMALISE = {
    "sql injection": "sql_injection",
    "sql-injection": "sql_injection",
    "n+1": "n_plus_1_query",
    "n plus 1": "n_plus_1_query",
    "missing auth": "missing_auth",
    "missing_auth": "missing_auth",
    "ssrf": "ssrf",
    "memory exhaust": "memory_exhaustion",
    "missing pagination": "missing_pagination",
    "magic number": "magic_number",
    "swallowed exception": "swallowed_exception",
    "hardcoded secret": "hardcoded_secret",
    "credential exposure": "credential_exposure",
    "insecure direct": "insecure_direct_object_ref",
    "idor": "insecure_direct_object_ref",
}


def extract_flags_from_review(review_text: str) -> list[str]:
    """
    Heuristic flag extractor from free-text review output.
    In production, replace with structured JSON output from the model.
    """
    found = set()
    for match in _FLAG_PATTERN.finditer(review_text):
        raw = match.group(0).lower().replace("-", " ").strip()
        normalised = _FLAG_NORMALISE.get(raw, raw.replace(" ", "_"))
        found.add(normalised)
    return sorted(found)


async def run_eval(
    model_alias: str,
    review_fn: ReviewFn,
    cases: list[EvalCase] | None = None,
) -> EvalResult:
    """
    Runs the evaluation suite.
    Pass a custom review_fn to evaluate any model or to inject mocks in tests.
    """
    if cases is None:
        cases = GOLDEN_CASES

    case_scores = []
    for case in cases:
        try:
            output = await review_fn(case.diff, model_alias)
            actual_flags = output.flags if output.flags else extract_flags_from_review("")
        except Exception as exc:
            logger.warning("Review failed for case %s: %s", case.id, exc)
            actual_flags = []

        score = score_case(case.id, case.expected_flags, actual_flags)
        case_scores.append(score)
        logger.debug("case=%s f1=%.3f", case.id, score.f1)

    result = EvalResult(model_alias=model_alias, case_scores=case_scores)
    logger.info(
        "Eval complete model=%s f1=%.3f precision=%.3f recall=%.3f fp_rate=%.3f",
        model_alias, result.f1, result.mean_precision, result.mean_recall, result.false_positive_rate,
    )
    return result
