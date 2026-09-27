"""Showcase tabs — built from the loaded config, so the page shows what actually runs.

A route opts into a tab with a ``showcase:`` block (extra keys on a route are
allowed and ignored by the pipeline)::

    routes:
      underwriting:
        provider: us_llm
        pipeline: {ingress: [pii, residency_ca]}
        showcase:
          tab: residency            # routes with the same tab share it
          title: Residency + approval
          order: 4
          blurb: Personal data headed to a US endpoint waits for a reviewer.
          label: Underwriting (US endpoint)
          presets:
            - {label: Clean question, prompt: What is our refund policy?}

Each tab carries, per route, the YAML that configures it — the route, its
provider and the guardrails it lists, with secrets redacted — so a visitor
sees the configuration behind every result. Without any ``showcase:`` blocks,
every route gets a plain tab of its own.
"""

from __future__ import annotations

from typing import Any

import yaml

from aegis_core.config.models import AegisConfig, PipelineConfig


def _guardrails_used(stages: PipelineConfig) -> list[str]:
    names: list[str] = []
    for stage in (stages.ingress, stages.egress):
        for entry in stage:
            base = entry.split(".", 1)[0]  # "pii.unmask" → "pii"
            if base not in names:
                names.append(base)
    return names


def route_yaml(cfg: AegisConfig, route_name: str) -> str:
    """The slice of ``aegis.yaml`` that configures *route_name* (secrets redacted)."""
    safe = cfg.safe_dict()
    route = cfg.routes[route_name]
    stages = route.pipeline if route.pipeline is not None else cfg.pipeline
    route_dict = {k: v for k, v in safe["routes"][route_name].items() if k != "showcase" and v}
    snippet: dict[str, Any] = {
        "providers": {route.provider: _compact(safe["providers"][route.provider])},
    }
    used = [g for g in _guardrails_used(stages) if g in safe["guardrails"]]
    if used:
        snippet["guardrails"] = {g: _compact(safe["guardrails"][g]) for g in used}
    if route.pipeline is None and (cfg.pipeline.ingress or cfg.pipeline.egress):
        snippet["pipeline"] = _compact(safe["pipeline"])
    snippet["routes"] = {route_name: _compact(route_dict)}
    return yaml.safe_dump(snippet, sort_keys=False, allow_unicode=True, width=100)


def _compact(value: Any) -> Any:
    """Drop empty and default-None fields so the snippet reads like a hand-written config."""
    if isinstance(value, dict):
        return {k: _compact(v) for k, v in value.items() if v not in (None, [], {}, "")}
    if isinstance(value, list):
        return [_compact(v) for v in value]
    return value


def build_showcase(cfg: AegisConfig) -> list[dict[str, Any]]:
    """Tabs for the showcase page, ordered by ``order`` then name."""
    tabs: dict[str, dict[str, Any]] = {}
    declared = any(isinstance(getattr(r, "showcase", None), dict) for r in cfg.routes.values())
    for name, route in cfg.routes.items():
        meta = getattr(route, "showcase", None)
        if declared and not isinstance(meta, dict):
            continue  # a curated demo lists only the routes it describes
        meta = meta if isinstance(meta, dict) else {}
        tab_id = str(meta.get("tab", name))
        tab = tabs.setdefault(
            tab_id,
            {
                "id": tab_id,
                "title": str(meta.get("title", name)),
                "order": int(meta.get("order", 100)),
                "blurb": str(meta.get("blurb", "")),
                "routes": [],
            },
        )
        tab["routes"].append(
            {
                "route": name,
                "label": str(meta.get("label", name)),
                "presets": [
                    {"label": str(p.get("label", "")), "prompt": str(p.get("prompt", ""))}
                    for p in meta.get("presets", [])
                    if isinstance(p, dict) and p.get("prompt")
                ],
                "config": route_yaml(cfg, name),
            }
        )
    return sorted(tabs.values(), key=lambda t: (t["order"], t["id"]))
