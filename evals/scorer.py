"""Precision / recall / F1 scorer for PR review evaluation."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class ReviewOutput:
    flags: list[str]
    severity: Optional[str] = None


@dataclass
class CaseScore:
    case_id: str
    precision: float
    recall: float
    f1: float
    false_positive: bool
    false_negative: bool


@dataclass
class EvalResult:
    model_alias: str
    case_scores: list[CaseScore]

    @property
    def mean_precision(self) -> float:
        return _mean([s.precision for s in self.case_scores])

    @property
    def mean_recall(self) -> float:
        return _mean([s.recall for s in self.case_scores])

    @property
    def f1(self) -> float:
        p, r = self.mean_precision, self.mean_recall
        if p + r == 0:
            return 0.0
        return 2 * p * r / (p + r)

    @property
    def false_positive_rate(self) -> float:
        fp_cases = [s for s in self.case_scores if s.false_positive]
        return len(fp_cases) / len(self.case_scores) if self.case_scores else 0.0

    def beats_baseline(self, baseline: "EvalResult", margin: float = 0.05) -> bool:
        """Quality gate: new model must beat baseline F1 by ≥5% to deploy."""
        return self.f1 >= baseline.f1 * (1 + margin)


def score_case(case_id: str, expected_flags: list[str], actual_flags: list[str]) -> CaseScore:
    expected = set(expected_flags)
    actual = set(actual_flags)

    true_positives = expected & actual
    false_positives = actual - expected
    false_negatives = expected - actual

    precision = len(true_positives) / len(actual) if actual else (1.0 if not expected else 0.0)
    recall = len(true_positives) / len(expected) if expected else (1.0 if not actual else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return CaseScore(
        case_id=case_id,
        precision=precision,
        recall=recall,
        f1=f1,
        false_positive=bool(false_positives and not expected),
        false_negative=bool(false_negatives),
    )


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
