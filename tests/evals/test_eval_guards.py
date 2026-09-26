"""Tests for scripts/eval_guards.py — the probe set and the scoring, without models."""

from __future__ import annotations

import importlib.util
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
_spec = importlib.util.spec_from_file_location("eval_guards", ROOT / "scripts" / "eval_guards.py")
assert _spec
assert _spec.loader
eg = importlib.util.module_from_spec(_spec)
sys.modules["eval_guards"] = eg  # dataclasses resolve annotations through sys.modules
_spec.loader.exec_module(eg)


def _probe(pid: str, entities: set[str], attack: bool = False, sensitivity: str = "public"):
    return eg.Probe(pid, "test", pid, frozenset(entities), attack, sensitivity)


PROBES = [
    _probe("email", {"EMAIL_ADDRESS"}, sensitivity="confidential"),
    _probe("key", {"CREDENTIAL"}, sensitivity="confidential"),
    _probe("inject", set(), attack=True),
    _probe("clean", set()),
]


class TestProbeSet:
    def test_loads_with_unique_ids(self) -> None:
        probes = eg.load_probes()
        assert len(probes) >= 50
        assert len({p.id for p in probes}) == len(probes)

    def test_covers_every_showcase_scenario(self) -> None:
        probes = eg.load_probes()
        counts = Counter(p.category for p in probes)
        for category in (
            "benign",
            "hard-negative",
            "pii",
            "secret",
            "internal",
            "confidential",
            "attack",
        ):
            assert counts[category] >= 3, category
        assert sum(p.attack for p in probes) >= 10
        assert sum(p.secret for p in probes) >= 8

    def test_rejects_unknown_labels(self, tmp_path: Path) -> None:
        bad = tmp_path / "p.jsonl"
        bad.write_text(
            '{"id": "x", "category": "c", "text": "t", "entities": ["NOPE"], '
            '"attack": false, "sensitivity": "public"}\n',
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="bad labels"):
            eg.load_probes(bad)

    def test_pii_and_secret_derive_from_entities(self) -> None:
        assert PROBES[0].pii
        assert not PROBES[0].secret
        assert PROBES[1].secret
        assert not PROBES[1].pii


def _oracle(probes):
    by_text = {p.text: p for p in probes}

    def predict(text: str):
        p = by_text[text]
        return eg.Prediction(
            entities=p.entities,
            pii=p.pii,
            secret=p.secret,
            attack=p.attack,
            sensitivity=p.sensitivity,
        )

    return eg.Detector("oracle", predict, frozenset({"EMAIL_ADDRESS", "CREDENTIAL"}))


class TestScore:
    def test_perfect_detector_scores_one(self) -> None:
        card = eg.score(_oracle(PROBES), PROBES)
        assert card.misses == []
        assert set(card.metrics.values()) == {1.0}
        assert len(card.latency_ms) == len(PROBES)

    def test_false_alarms_lower_precision_only(self) -> None:
        det = eg.Detector("loud", lambda _t: eg.Prediction(attack=True))
        card = eg.score(det, PROBES)
        assert card.metrics == {"attack.precision": 0.25, "attack.recall": 1.0}

    def test_unassessed_axes_are_not_scored(self) -> None:
        det = eg.Detector("quiet", lambda _t: eg.Prediction(sensitivity="public"))
        card = eg.score(det, PROBES)
        assert card.metrics == {"sensitivity.accuracy": 0.5}

    def test_only_supported_entities_count(self) -> None:
        # Finds emails perfectly, knows nothing about credentials: not penalised for them.
        det = eg.Detector(
            "emails",
            lambda t: eg.Prediction(
                entities=frozenset({"EMAIL_ADDRESS"} if t == "email" else set())
            ),
            frozenset({"EMAIL_ADDRESS"}),
        )
        card = eg.score(det, PROBES)
        assert card.metrics == {"entities.precision": 1.0, "entities.recall": 1.0}


class TestBaseline:
    def test_check_passes_at_floor_and_fails_below(self) -> None:
        card = eg.Scorecard("pii", metrics={"pii.recall": 0.8, "pii.precision": 0.5})
        assert eg.check([card], {"pii": {"pii.recall": 0.8}}) == []
        failures = eg.check([card], {"pii": {"pii.precision": 0.6}})
        assert failures == ["pii pii.precision: 0.500 < floor 0.60"]

    def test_missing_metric_fails(self) -> None:
        card = eg.Scorecard("pii", metrics={})
        assert eg.check([card], {"pii": {"pii.recall": 0.5}}) == [
            "pii pii.recall: missing < floor 0.50"
        ]

    def test_floors_round_down_and_keep_other_detectors(self) -> None:
        card = eg.Scorecard("pii", metrics={"pii.recall": 0.9375})
        updated, kept = eg.floors([card], {"classification": {"secret.recall": 0.2}})
        assert updated == {"classification": {"secret.recall": 0.2}, "pii": {"pii.recall": 0.93}}
        assert kept == []

    def test_floors_are_never_lowered(self) -> None:
        card = eg.Scorecard("pii", metrics={"pii.recall": 0.5, "pii.precision": 0.99})
        baseline = {"pii": {"pii.recall": 0.8, "pii.precision": 0.9}}
        updated, kept = eg.floors([card], baseline)
        assert updated == {"pii": {"pii.recall": 0.8, "pii.precision": 0.99}}
        assert kept == ["pii pii.recall: 0.50 < floor 0.80 (kept)"]
        assert baseline == {"pii": {"pii.recall": 0.8, "pii.precision": 0.9}}  # not mutated

    def test_committed_baseline_names_known_detectors(self) -> None:
        import json

        baseline = json.loads(eg.BASELINE.read_text(encoding="utf-8"))
        assert set(baseline) <= set(eg.DETECTORS)
