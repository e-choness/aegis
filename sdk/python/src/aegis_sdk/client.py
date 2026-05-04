from __future__ import annotations
import asyncio
import time
from typing import Optional
import httpx
from .errors import (
    AIPlatformError,
    AuthenticationError,
    BudgetExceededError,
    DataResidencyError,
    JobTimeoutError,
    ModelUnavailableError,
    RateLimitError,
)
from .types import InferenceRequest, JobResult, PollOptions, ReviewPROptions


class AIPlatformClient:
    """
    Async client for the Aegis AI Gateway.
    All LLM calls go through the gateway — never directly to a model provider.
    """

    def __init__(self, sso_token: str, base_url: str = "http://localhost:8000") -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {sso_token}",
        }
        self._client = httpx.AsyncClient(timeout=30.0)

    async def submit_inference(self, request: InferenceRequest) -> str:
        """Submit an inference job. Returns the job_id for polling."""
        payload = {
            "prompt": request.prompt,
            "task_type": request.task_type,
            "team_id": request.team_id,
            "user_id": request.user_id,
        }
        if request.trace_id is not None:
            payload["trace_id"] = request.trace_id
        if request.model_alias is not None:
            payload["model_alias"] = request.model_alias
        if request.max_tokens != 2048:
            payload["max_tokens"] = request.max_tokens

        response = await self._client.post(
            f"{self._base_url}/api/v1/inference",
            json=payload,
            headers=self._headers,
        )
        self._assert_ok(response)
        return response.json()["job_id"]

    async def review_pr(self, options: ReviewPROptions) -> str:
        """Submit a PR review job. Returns job_id."""
        return await self.submit_inference(
            InferenceRequest(
                prompt=options.diff_url,
                task_type="pr_review",
                team_id=options.team_id,
                user_id=options.user_id,
                trace_id=options.trace_id,
            )
        )

    async def poll_job(
        self,
        job_id: str,
        options: Optional[PollOptions] = None,
    ) -> JobResult:
        """Poll until job completes or fails. Raises JobTimeoutError on timeout."""
        opts = options or PollOptions()
        deadline = time.monotonic() + opts.timeout

        while time.monotonic() < deadline:
            response = await self._client.get(
                f"{self._base_url}/api/v1/jobs/{job_id}",
                headers=self._headers,
            )
            self._assert_ok(response)

            data = response.json()
            job = JobResult(
                job_id=data["job_id"],
                status=data["status"],
                result=data.get("result"),
                error=data.get("error"),
                model_used=data.get("model_used"),
                cost_usd=data.get("cost_usd"),
            )
            if job.status in ("completed", "failed"):
                return job

            await asyncio.sleep(opts.poll_interval)

        raise JobTimeoutError(job_id)

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "AIPlatformClient":
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()

    def _assert_ok(self, response: httpx.Response) -> None:
        if response.is_success:
            return
        trace_id = response.headers.get("x-trace-id")
        status = response.status_code
        if status == 401:
            raise AuthenticationError(trace_id)
        if status == 402:
            raise BudgetExceededError(trace_id)
        if status == 429:
            retry_after = int(response.headers.get("retry-after", "60"))
            raise RateLimitError(retry_after, trace_id)
        if status == 451:
            raise DataResidencyError(trace_id)
        if status == 503:
            raise ModelUnavailableError(trace_id)
        raise AIPlatformError(f"HTTP {status}", status, trace_id)
