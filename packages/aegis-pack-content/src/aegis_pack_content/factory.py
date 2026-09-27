"""Pack factory for aegis.content — registered under the aegis.packs entry-point group."""

from __future__ import annotations

from collections.abc import Mapping
from importlib.metadata import entry_points
from typing import Any

from aegis_core.errors import AegisConfigValidationError
from aegis_core.packs import GuardrailConfig
from aegis_core.pipeline.protocol import PipelineNode

DEFAULT_BACKEND = "gliner2"
_RESERVED = {"pack", "mode", "scanners", "threshold", "model", "backend", "entities", "labels"}


def _entities(raw: Any, name: str) -> dict[str, str]:
    """``entities`` as a list of labels, or a map of label → description."""
    if raw is None:
        return {}
    if isinstance(raw, list) and all(isinstance(x, str) for x in raw):
        return {x: x for x in raw}
    if isinstance(raw, Mapping) and all(isinstance(k, str) for k in raw):
        return {k: str(v) if v else k for k, v in raw.items()}
    raise AegisConfigValidationError(
        f"guardrail {name!r}: entities must be a list of labels or a map of label → description.",
        guardrail=name,
    )


def _tasks(raw: Any, name: str) -> dict[str, list[str]]:
    """``labels`` as a map of task → list of at least two values."""
    if raw is None:
        return {}
    if isinstance(raw, Mapping) and all(
        isinstance(k, str) and isinstance(v, list) and len(v) >= 2 for k, v in raw.items()
    ):
        return {k: [str(x) for x in v] for k, v in raw.items()}
    raise AegisConfigValidationError(
        f"guardrail {name!r}: labels must map each task to a list of two or more values, "
        "e.g. sensitivity: [public, internal, confidential].",
        guardrail=name,
    )


def load_backend(backend: str, model_id: str | None, options: Mapping[str, Any]) -> Any:
    """Instantiate a backend registered under ``aegis.content_models``."""
    matches = [ep for ep in entry_points(group="aegis.content_models") if ep.name == backend]
    if not matches:
        known = sorted(ep.name for ep in entry_points(group="aegis.content_models"))
        raise ValueError(f"unknown content backend {backend!r}; installed: {', '.join(known)}")
    cls = matches[0].load()
    return cls(model_id, options) if model_id else cls(options=options)


def from_config(name: str, cfg: GuardrailConfig) -> dict[str, list[PipelineNode]]:
    """Return a ContentNode in ingress, and an unmask node in egress if it masks entities.

    ``aegis.yaml`` fields (beyond ``pack``):

    ``model``
        Model id for the backend (default ``fastino/gliner2-base-v1``).
    ``backend``
        ``gliner2`` (default) or another ``aegis.content_models`` entry point.
    ``entities``
        Entity types to mask: a list, or a map of label → description.
    ``labels``
        Classification tasks: a map of task → allowed values. The answer goes
        to ``state.labels[task]`` for ``aegis.policy`` to act on.
    ``threshold``
        Minimum entity confidence, 0-1 (default 0.5).

    Anything else is passed to the backend.
    """
    from aegis_core.masking import UnmaskNode
    from aegis_pack_content.node import ContentNode

    entities = _entities(getattr(cfg, "entities", None), name)
    tasks = _tasks(getattr(cfg, "labels", None), name)
    if not entities and not tasks:
        raise AegisConfigValidationError(
            f"guardrail {name!r}: aegis.content needs 'entities', 'labels', or both.",
            guardrail=name,
        )
    threshold = cfg.threshold if cfg.threshold is not None else 0.5
    if not 0.0 <= threshold <= 1.0:
        raise AegisConfigValidationError(
            f"guardrail {name!r}: threshold must be between 0 and 1, got {threshold}.",
            guardrail=name,
        )

    backend = str(getattr(cfg, "backend", None) or DEFAULT_BACKEND)
    extra = {k: v for k, v in (cfg.model_extra or {}).items() if k not in _RESERVED}
    try:
        if backend == DEFAULT_BACKEND:
            from aegis_pack_content.gliner import ensure_installed

            ensure_installed()  # fail at startup, not on the first request
        model = load_backend(
            backend, getattr(cfg, "model", None), {"threshold": threshold, **extra}
        )
    except ValueError as exc:
        raise AegisConfigValidationError(f"guardrail {name!r}: {exc}", guardrail=name) from exc

    stages: dict[str, list[PipelineNode]] = {
        "ingress": [ContentNode(model, entities=entities, tasks=tasks, name=name)]
    }
    if entities:
        stages["egress"] = [UnmaskNode(name=f"{name}.unmask")]
    return stages
