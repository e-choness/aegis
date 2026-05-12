from __future__ import annotations
import asyncio
import logging
import time
import uuid
from typing import Optional, Dict

from ..models import AuditRecord, InferenceRequest, JobResult
from ..providers.base import CompletionRequest
from ..providers.factory import ProviderFactory
from ..telemetry import (
    budget_utilization_ratio,
    inference_cost_usd_total,
    inference_latency_seconds,
    pii_detections_total,
    requests_total,
    restricted_cloud_violations_total,
)
from .audit import AuditLogger
from .budget import BudgetService
from .classifier import DataClassifier
from .health import ProviderHealth
from .pii import PIIMasker
from .router import ModelRouter
from .model_lifecycle import ModelLifecycleManager

logger = logging.getLogger("aegis.inference")

_PR_REVIEW_SYSTEM = (
    "You are an expert code reviewer. Analyse the provided diff and identify: "
    "security vulnerabilities, performance issues, logic errors, and style violations. "
    "Be specific: cite file names and line numbers. Format as a concise markdown list."
)


class InferenceService:
    """
    Orchestrates the full gateway pipeline (ADR-005 async-first).
    Steps match the numbered flow in the Solution Architect doc.
    Supports Tier 2 external LLM provider routing for RESTRICTED data.
    """

    def __init__(
        self,
        health: Optional[ProviderHealth] = None,
        budget: Optional[BudgetService] = None,
        audit: Optional[AuditLogger] = None,
        pii_masker: Optional[PIIMasker] = None,
        external_llm_provider=None,
        model_lifecycle: Optional[ModelLifecycleManager] = None,
        model_aliases: Optional[Dict[str, str]] = None,
    ) -> None:
        self._health = health or ProviderHealth()
        self._budget = budget or BudgetService()
        self._audit = audit or AuditLogger()
        self._classifier = DataClassifier()
        self._router = ModelRouter(health_checker=self._health)
        self._pii_masker = pii_masker or PIIMasker()
        self._jobs: dict[str, JobResult] = {}
        self._external_llm = external_llm_provider
        self._model_lifecycle = model_lifecycle
        self._model_aliases = model_aliases or {}

    def enqueue(self, request: InferenceRequest) -> str:
        job_id = str(uuid.uuid4())
        trace_id = request.trace_id or str(uuid.uuid4())
        self._jobs[job_id] = JobResult(job_id=job_id, status="queued")
        asyncio.create_task(self._run(job_id, trace_id, request))
        return job_id

    def get_job(self, job_id: str) -> Optional[JobResult]:
        return self._jobs.get(job_id)

    def _resolve_model_alias(self, model_alias: Optional[str]) -> Optional[str]:
        """Resolve model alias (haiku/sonnet/opus) to actual Tier 2 model ID."""
        if not model_alias:
            return None
        return self._model_aliases.get(model_alias.lower())

    async def _call_tier2(
        self, job_id: str, trace_id: str, request: InferenceRequest,
        model_alias: str, tier2_model_id: str
    ) -> None:
        """Call Tier 2 external LLM provider for RESTRICTED data."""
        if not self._external_llm:
            self._jobs[job_id] = JobResult(
                job_id=job_id,
                status="failed",
                error="Tier 2 not available for RESTRICTED data",
            )
            return

        start = time.monotonic()
        try:
            logger.info("Routing RESTRICTED data to Tier 2 (model=%s)", tier2_model_id)

            # Call Tier 2 provider
            response = await self._external_llm.complete(CompletionRequest(
                model_id=tier2_model_id,
                prompt=request.prompt,
            ))
            self._health.record_success("external_llm")

            # Cost accounting (Tier 2 is zero cost)
            cost_usd = 0.0

            # Metrics
            latency_ms = int((time.monotonic() - start) * 1000)
            requests_total.labels(
                team_id=request.team_id,
                model_alias=model_alias,
                provider="external_llm",
                tier="2",
                status="completed",
            ).inc()
            inference_latency_seconds.labels(
                model_alias=model_alias,
                provider="external_llm",
            ).observe(latency_ms / 1000)

            # Audit
            self._audit.log(AuditRecord(
                trace_id=trace_id,
                user_id=request.user_id,
                team_id=request.team_id,
                model_alias=model_alias,
                model_id=tier2_model_id,
                provider="external_llm",
                tier=2,
                data_classification="RESTRICTED",
                cost_usd=cost_usd,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                cache_hit=False,
                pii_detected=False,
                latency_ms=latency_ms,
            ))

            self._jobs[job_id] = JobResult(
                job_id=job_id,
                status="completed",
                content=response.content,
                model_alias=model_alias,
                provider="external_llm",
                tier=2,
                cost_usd=cost_usd,
                data_classification="RESTRICTED",
            )

        except Exception as exc:
            self._health.record_failure("external_llm")
            requests_total.labels(
                team_id=request.team_id,
                model_alias=model_alias,
                provider="external_llm",
                tier="2",
                status="error",
            ).inc()
            logger.error("Tier 2 call failed for %s: %s", job_id, exc)
            self._jobs[job_id] = JobResult(
                job_id=job_id,
                status="failed",
                error=str(exc),
            )

    async def _run(self, job_id: str, trace_id: str, request: InferenceRequest) -> None:
        self._jobs[job_id] = JobResult(job_id=job_id, status="running")
        start = time.monotonic()
        provider_name = "unknown"
        model_alias = "unknown"
        tier = 0

        try:
            # Step 2 — Classify
            classification = self._classifier.classify(request.prompt)

            # Step 3 — PII masking
            masked_prompt, mask_map = self._pii_masker.mask(request.prompt)
            pii_detected = bool(mask_map)
            for entity_type in {v.split("_")[0] for v in mask_map} if mask_map else set():
                pii_detections_total.labels(entity_type=entity_type).inc()

            # Step 4a — Handle RESTRICTED data → Tier 2 only
            if classification == "RESTRICTED":
                # Resolve model alias if provided, otherwise default
                requested_alias = (request.model or "").lower() if request.model else None
                tier2_model_id = self._resolve_model_alias(requested_alias)

                if not tier2_model_id:
                    # Default to opus for RESTRICTED
                    tier2_model_id = self._resolve_model_alias("opus")

                if tier2_model_id:
                    model_alias = requested_alias or "opus"
                    logger.info(
                        "RESTRICTED data detected — routing to Tier 2 (model=%s, alias=%s)",
                        tier2_model_id, model_alias
                    )
                    await self._call_tier2(job_id, trace_id, request, model_alias, tier2_model_id)
                    return
                else:
                    raise ValueError("No Tier 2 model available for RESTRICTED data")

            # Step 5 — Route non-RESTRICTED data (Tier 1 first, Tier 2 fallback)
            model_config = self._router.route(
                request.task_type, request.complexity, classification,
                self._budget.get_remaining(request.team_id),
            )
            provider_name = model_config.provider
            model_alias = model_config.alias
            tier = model_config.tier

            estimated_cost = model_config.cost_input_per_mtok * 2000 / 1_000_000
            ok, reason = self._budget.check(request.team_id, estimated_cost)
            if not ok:
                requests_total.labels(
                    team_id=request.team_id, model_alias=model_alias,
                    provider=provider_name, tier=str(tier), status="budget_exceeded",
                ).inc()
                self._jobs[job_id] = JobResult(job_id=job_id, status="failed", error=reason)
                return

            # Step 8 — Call provider (with masked prompt)
            provider = ProviderFactory.get(model_config.provider)
            system = _PR_REVIEW_SYSTEM if request.task_type == "pr_review" else None
            response = await provider.complete(CompletionRequest(
                model_id=model_config.model_id,
                prompt=masked_prompt,
                system_prompt=system,
            ))
            self._health.record_success(model_config.provider)

            # Step 9 — Scan output for PII leakage
            leaked = self._pii_masker.scan_output(response.content)
            if leaked:
                logger.error("PII leakage in provider output — trace_id=%s types=%s", trace_id, leaked)

            # Step 10 — Unmask PII in response
            final_content = self._pii_masker.unmask(response.content, mask_map)

            # Step 12 — Cost accounting
            actual_cost = provider.estimate_cost_usd(
                response.input_tokens, response.output_tokens, model_config.alias
            )
            self._budget.record_spend(request.team_id, actual_cost)

            # Metrics
            latency_ms = int((time.monotonic() - start) * 1000)
            requests_total.labels(
                team_id=request.team_id, model_alias=model_alias,
                provider=provider_name, tier=str(tier), status="completed",
            ).inc()
            inference_cost_usd_total.labels(
                team_id=request.team_id, model_alias=model_alias,
                provider=provider_name, tier=str(tier),
            ).inc(actual_cost)
            inference_latency_seconds.labels(
                model_alias=model_alias, provider=provider_name,
            ).observe(latency_ms / 1000)

            utilization = self._budget.utilization(request.team_id)
            if utilization is not None:
                budget_utilization_ratio.labels(team_id=request.team_id).set(utilization)

            # Compliance alert: RESTRICTED data to cloud tier is a hard violation
            if classification == "RESTRICTED" and tier == 1:
                restricted_cloud_violations_total.inc()
                logger.critical(
                    "RESTRICTED data routed to cloud! trace_id=%s provider=%s",
                    trace_id, provider_name,
                )

            # Step 13 — Audit log
            self._audit.log(AuditRecord(
                trace_id=trace_id,
                user_id=request.user_id,
                team_id=request.team_id,
                model_alias=model_alias,
                model_id=model_config.model_id,
                provider=provider_name,
                tier=tier,
                data_classification=classification,
                cost_usd=actual_cost,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                cache_hit=response.cache_hit,
                pii_detected=pii_detected,
                latency_ms=latency_ms,
            ))

            self._jobs[job_id] = JobResult(
                job_id=job_id,
                status="completed",
                content=final_content,
                model_alias=model_alias,
                provider=provider_name,
                tier=tier,
                cost_usd=actual_cost,
                data_classification=classification,
            )

        except Exception as exc:
            self._health.record_failure(provider_name)
            requests_total.labels(
                team_id=request.team_id, model_alias=model_alias,
                provider=provider_name, tier=str(tier), status="error",
            ).inc()
            logger.exception("Inference job %s failed", job_id)
            self._jobs[job_id] = JobResult(job_id=job_id, status="failed", error=str(exc))
