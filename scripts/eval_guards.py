"""Measure content detectors against a labelled probe set.

    uv run python scripts/eval_guards.py pii classification           # print the scorecard
    uv run python scripts/eval_guards.py pii classification --check   # CI: fail below baseline
    uv run python scripts/eval_guards.py pii --update-baseline        # after an improvement

Each probe in ``evals/probes.jsonl`` is labelled with the entity types it
contains, whether it is an attack (prompt injection, jailbreak, poisoned
document, tool exfiltration) and how sensitive it is. ``pii`` and ``secret``
are derived from the entities, so the labels can't contradict each other.

A detector is scored only on what it claims to detect: the PII pack is not
penalised for missing credentials, nor classification for lacking entities.
Quality floors live in ``evals/baseline.json``; ``--check`` fails when any
metric drops below its floor. Latency is reported but not gated — it depends
on the machine.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import sys
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROBES = ROOT / "evals" / "probes.jsonl"
BASELINE = ROOT / "evals" / "baseline.json"

#: Entity types that identify a person; ``pii`` is true when a probe has one.
PERSONAL = frozenset(
    {
        "PERSON",
        "EMAIL_ADDRESS",
        "PHONE_NUMBER",
        "LOCATION",
        "STREET_ADDRESS",
        "POSTAL_CODE",
        "IP_ADDRESS",
        "CREDIT_CARD",
        "IBAN_CODE",
        "US_SSN",
        "CA_SIN",
    }
)
#: Entity types that grant access; ``secret`` is true when a probe has one.
SECRETS = frozenset({"CREDENTIAL"})
KNOWN_ENTITIES = PERSONAL | SECRETS | {"INTERNAL_HOST"}
SENSITIVITY = ("public", "internal", "confidential")


@dataclass(frozen=True)
class Probe:
    id: str
    category: str
    text: str
    entities: frozenset[str]
    attack: bool
    sensitivity: str

    @property
    def pii(self) -> bool:
        return bool(self.entities & PERSONAL)

    @property
    def secret(self) -> bool:
        return bool(self.entities & SECRETS)


@dataclass
class Prediction:
    """What a detector said about one probe; ``None`` means "not assessed"."""

    entities: frozenset[str] | None = None
    pii: bool | None = None
    secret: bool | None = None
    attack: bool | None = None
    sensitivity: str | None = None


@dataclass
class Detector:
    name: str
    predict: Callable[[str], Prediction]
    #: Entity types this detector can find; others are left out of its score.
    entities: frozenset[str] = frozenset()


def load_probes(path: Path = PROBES) -> list[Probe]:
    probes = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        unknown = set(row["entities"]) - KNOWN_ENTITIES
        if unknown or row["sensitivity"] not in SENSITIVITY:
            raise ValueError(
                f"{path.name}:{n}: bad labels {sorted(unknown)} / {row['sensitivity']}"
            )
        probes.append(
            Probe(
                id=row["id"],
                category=row["category"],
                text=row["text"],
                entities=frozenset(row["entities"]),
                attack=row["attack"],
                sensitivity=row["sensitivity"],
            )
        )
    return probes


# ── Metrics ───────────────────────────────────────────────────────────────────


@dataclass
class Counts:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    def add(self, expected: bool, predicted: bool) -> None:
        self.tp += expected and predicted
        self.fp += predicted and not expected
        self.fn += expected and not predicted

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 1.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 1.0


@dataclass
class Scorecard:
    detector: str
    metrics: dict[str, float] = field(default_factory=dict)
    per_entity: dict[str, Counts] = field(default_factory=dict)
    misses: list[str] = field(default_factory=list)
    latency_ms: list[float] = field(default_factory=list)


def score(detector: Detector, probes: Iterable[Probe]) -> Scorecard:
    card = Scorecard(detector.name)
    entities = Counts()
    binary = {"pii": Counts(), "secret": Counts(), "attack": Counts()}
    sens_right = sens_total = 0

    probes = list(probes)
    if probes:
        detector.predict(probes[0].text)  # warm-up: model loading isn't latency
    for probe in probes:
        start = time.perf_counter()
        pred = detector.predict(probe.text)
        card.latency_ms.append((time.perf_counter() - start) * 1000)

        if pred.entities is not None:
            for etype in detector.entities:
                expected, found = etype in probe.entities, etype in pred.entities
                entities.add(expected, found)
                card.per_entity.setdefault(etype, Counts()).add(expected, found)
                if expected != found:
                    card.misses.append(f"{probe.id}: {'missed' if expected else 'false'} {etype}")
        for axis, counts in binary.items():
            got = getattr(pred, axis)
            if got is not None:
                want = getattr(probe, axis)
                counts.add(want, got)
                if want != got:
                    card.misses.append(f"{probe.id}: {axis} {'missed' if want else 'false alarm'}")
        if pred.sensitivity is not None:
            sens_total += 1
            sens_right += pred.sensitivity == probe.sensitivity
            if pred.sensitivity != probe.sensitivity:
                card.misses.append(
                    f"{probe.id}: sensitivity {pred.sensitivity} (want {probe.sensitivity})"
                )

    if entities.tp + entities.fp + entities.fn:
        card.metrics["entities.precision"] = entities.precision
        card.metrics["entities.recall"] = entities.recall
    for axis, counts in binary.items():
        if counts.tp + counts.fp + counts.fn:
            card.metrics[f"{axis}.precision"] = counts.precision
            card.metrics[f"{axis}.recall"] = counts.recall
    if sens_total:
        card.metrics["sensitivity.accuracy"] = sens_right / sens_total
    return card


# ── Detectors ─────────────────────────────────────────────────────────────────


def _pii() -> Detector:
    from aegis_pack_pii import PiiDetector
    from aegis_pack_pii.detection import DEFAULT_ENTITIES

    detector = PiiDetector()

    def predict(text: str) -> Prediction:
        found = frozenset(r.entity_type for r in detector.find(text))
        return Prediction(entities=found, pii=bool(found & PERSONAL))

    return Detector("pii", predict, frozenset(DEFAULT_ENTITIES) & KNOWN_ENTITIES)


def _classification() -> Detector:
    from aegis_pack_classification.node import ClassificationNode

    from aegis_core.pipeline.state import RunState
    from aegis_core.providers.models import Message

    node = ClassificationNode()

    def predict(text: str) -> Prediction:
        state = RunState(run_id="eval", route="eval", messages=[Message(role="user", content=text)])
        delta = asyncio.run(node.run(state))
        label = (delta.labels or {}).get("classification", "public")
        return Prediction(
            pii=label in ("pii", "financial"),  # card numbers are personal data
            secret=label == "secret",
            sensitivity="public" if label == "public" else "confidential",
        )

    return Detector("classification", predict)


CONTENT_CONFIG = ROOT / "evals" / "content.yaml"
#: aegis.content placeholder types → the probe vocabulary.
_CONTENT_ENTITIES = {"CREDENTIAL": "CREDENTIAL", "INTERNAL_HOSTNAME": "INTERNAL_HOST"}


def _content() -> Detector:
    """The model-backed pack, configured exactly as ``evals/content.yaml`` (needs ``--group models``)."""
    import yaml
    from aegis_pack_content.factory import from_config
    from aegis_pack_content.node import ContentNode, entity_type

    from aegis_core.config.models import GuardrailConfig

    raw = yaml.safe_load(CONTENT_CONFIG.read_text(encoding="utf-8"))["guardrails"]["content"]
    node = from_config("content", GuardrailConfig.model_validate(raw))["ingress"][0]
    assert isinstance(node, ContentNode)

    # Score only what the config asks the model for.
    supported = frozenset(
        _CONTENT_ENTITIES[t]
        for label in node.entities
        if (t := entity_type(label)) in _CONTENT_ENTITIES
    )

    def predict(text: str) -> Prediction:
        analysis = node.model.analyze(text, node.entities, node.tasks)
        found = frozenset(
            _CONTENT_ENTITIES[t]
            for e in analysis.entities
            if (t := entity_type(e.label)) in _CONTENT_ENTITIES
        )
        intent = analysis.labels.get("intent")
        sensitivity = analysis.labels.get("sensitivity")
        return Prediction(
            entities=found,
            secret=("CREDENTIAL" in found) if "CREDENTIAL" in supported else None,
            attack=None
            if "intent" not in node.tasks
            else (intent is not None and "injection" in intent.value),
            sensitivity=sensitivity.value if sensitivity else None,
        )

    return Detector("content", predict, supported)


DETECTORS: dict[str, Callable[[], Detector]] = {
    "pii": _pii,
    "classification": _classification,
    "content": _content,
}


# ── Reporting ─────────────────────────────────────────────────────────────────


def _pct(x: float) -> str:
    return f"{x * 100:5.1f}%"


def render(card: Scorecard, verbose: bool) -> str:
    lat = sorted(card.latency_ms)
    p95 = lat[min(len(lat) - 1, math.ceil(0.95 * len(lat)) - 1)] if lat else 0.0
    lines = [f"## {card.detector}", "", "| metric | value |", "|---|---|"]
    lines += [f"| {k} | {_pct(v)} |" for k, v in card.metrics.items()]
    lines.append(
        f"| latency p50 / p95 | {statistics.median(lat) if lat else 0:.1f} / {p95:.1f} ms |"
    )
    if card.per_entity:
        lines += ["", "| entity | precision | recall | tp | fp | fn |", "|---|---|---|---|---|---|"]
        for etype, c in sorted(card.per_entity.items()):
            if c.tp + c.fp + c.fn:
                lines.append(
                    f"| {etype} | {_pct(c.precision)} | {_pct(c.recall)} | {c.tp} | {c.fp} | {c.fn} |"
                )
    if verbose and card.misses:
        lines += ["", "Misses:", *[f"- {m}" for m in card.misses]]
    return "\n".join(lines) + "\n"


def check(cards: list[Scorecard], baseline: dict[str, dict[str, float]]) -> list[str]:
    """Return one message per metric below its floor (or missing)."""
    failures = []
    for card in cards:
        for metric, floor in baseline.get(card.detector, {}).items():
            got = card.metrics.get(metric)
            if got is None or got + 1e-9 < floor:
                shown = "missing" if got is None else f"{got:.3f}"
                failures.append(f"{card.detector} {metric}: {shown} < floor {floor:.2f}")
    return failures


def floors(
    cards: list[Scorecard], baseline: dict[str, dict[str, float]]
) -> tuple[dict[str, dict[str, float]], list[str]]:
    """Raise floors to the current scores (rounded down to 2 places); never lower one.

    Returns the new baseline and one message per floor the current score is
    below — accepting such a drop (e.g. new probes a detector can't handle)
    means editing ``baseline.json`` by hand, so it shows up in review.
    """
    updated = {name: dict(metrics) for name, metrics in baseline.items()}
    kept = []
    for card in cards:
        current = updated.setdefault(card.detector, {})
        for metric, value in card.metrics.items():
            new = math.floor(value * 100) / 100
            old = current.get(metric)
            if old is not None and new < old:
                kept.append(f"{card.detector} {metric}: {new:.2f} < floor {old:.2f} (kept)")
            else:
                current[metric] = new
    return updated, kept


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure content detectors against evals/probes.jsonl."
    )
    parser.add_argument("detectors", nargs="+", choices=sorted(DETECTORS))
    parser.add_argument("--check", action="store_true", help="fail when below evals/baseline.json")
    parser.add_argument("--update-baseline", action="store_true", help="record current scores")
    parser.add_argument("-v", "--verbose", action="store_true", help="list every miss")
    args = parser.parse_args(argv)

    probes = load_probes()
    baseline = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else {}
    cards = [score(DETECTORS[name](), probes) for name in args.detectors]

    print(f"# Guard evals — {len(probes)} probes\n")
    for card in cards:
        print(render(card, args.verbose or args.check))

    if args.update_baseline:
        updated, kept = floors(cards, baseline)
        BASELINE.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")
        print(f"Updated {BASELINE.relative_to(ROOT)}")
        for message in kept:
            print(f"NOT LOWERED {message} — edit the file to accept it", file=sys.stderr)
        baseline = updated
    if args.check:
        failures = check(cards, baseline)
        for f in failures:
            print(f"FAIL {f}", file=sys.stderr)
        if failures:
            return 1
        print("All metrics at or above baseline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
