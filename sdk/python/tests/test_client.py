"""Python SDK tests — uses respx to mock httpx without touching the network."""
from __future__ import annotations
import pytest
import respx
import httpx
from aegis_sdk import (
    AIPlatformClient,
    AuthenticationError,
    BudgetExceededError,
    DataResidencyError,
    JobTimeoutError,
    ModelUnavailableError,
    RateLimitError,
    InferenceRequest,
    PollOptions,
    ReviewPROptions,
)

BASE = "http://gateway-test:8000"


def _client() -> AIPlatformClient:
    return AIPlatformClient(sso_token="test-token", base_url=BASE)


# ── submit_inference ──────────────────────────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_submit_inference_returns_job_id():
    respx.post(f"{BASE}/api/v1/inference").mock(
        return_value=httpx.Response(202, json={"job_id": "job-abc"})
    )
    async with _client() as c:
        job_id = await c.submit_inference(InferenceRequest(prompt="hello", team_id="t1", user_id="u1"))
    assert job_id == "job-abc"


@respx.mock
@pytest.mark.asyncio
async def test_submit_inference_auth_error():
    respx.post(f"{BASE}/api/v1/inference").mock(return_value=httpx.Response(401))
    async with _client() as c:
        with pytest.raises(AuthenticationError) as exc_info:
            await c.submit_inference(InferenceRequest(prompt="x", team_id="t", user_id="u"))
    assert exc_info.value.status_code == 401


@respx.mock
@pytest.mark.asyncio
async def test_submit_inference_budget_error():
    respx.post(f"{BASE}/api/v1/inference").mock(return_value=httpx.Response(402))
    async with _client() as c:
        with pytest.raises(BudgetExceededError):
            await c.submit_inference(InferenceRequest(prompt="x", team_id="t", user_id="u"))


@respx.mock
@pytest.mark.asyncio
async def test_submit_inference_rate_limit():
    respx.post(f"{BASE}/api/v1/inference").mock(
        return_value=httpx.Response(429, headers={"retry-after": "30"})
    )
    async with _client() as c:
        with pytest.raises(RateLimitError) as exc_info:
            await c.submit_inference(InferenceRequest(prompt="x", team_id="t", user_id="u"))
    assert exc_info.value.retry_after == 30


@respx.mock
@pytest.mark.asyncio
async def test_submit_inference_data_residency():
    respx.post(f"{BASE}/api/v1/inference").mock(return_value=httpx.Response(451))
    async with _client() as c:
        with pytest.raises(DataResidencyError):
            await c.submit_inference(InferenceRequest(prompt="x", team_id="t", user_id="u"))


@respx.mock
@pytest.mark.asyncio
async def test_submit_inference_model_unavailable():
    respx.post(f"{BASE}/api/v1/inference").mock(return_value=httpx.Response(503))
    async with _client() as c:
        with pytest.raises(ModelUnavailableError):
            await c.submit_inference(InferenceRequest(prompt="x", team_id="t", user_id="u"))


# ── poll_job ──────────────────────────────────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_poll_job_completed_immediately():
    respx.get(f"{BASE}/api/v1/jobs/job-123").mock(
        return_value=httpx.Response(200, json={
            "job_id": "job-123", "status": "completed",
            "result": "LGTM", "model_used": "haiku", "cost_usd": 0.001,
        })
    )
    async with _client() as c:
        job = await c.poll_job("job-123")
    assert job.status == "completed"
    assert job.result == "LGTM"
    assert job.cost_usd == 0.001


@respx.mock
@pytest.mark.asyncio
async def test_poll_job_pending_then_completed():
    call_count = 0

    def _side_effect(request):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(200, json={"job_id": "job-xyz", "status": "pending"})
        return httpx.Response(200, json={"job_id": "job-xyz", "status": "completed", "result": "ok"})

    respx.get(f"{BASE}/api/v1/jobs/job-xyz").mock(side_effect=_side_effect)
    async with _client() as c:
        job = await c.poll_job("job-xyz", PollOptions(timeout=10.0, poll_interval=0.01))
    assert job.status == "completed"
    assert call_count == 2


@respx.mock
@pytest.mark.asyncio
async def test_poll_job_timeout():
    respx.get(f"{BASE}/api/v1/jobs/job-slow").mock(
        return_value=httpx.Response(200, json={"job_id": "job-slow", "status": "pending"})
    )
    async with _client() as c:
        with pytest.raises(JobTimeoutError) as exc_info:
            await c.poll_job("job-slow", PollOptions(timeout=0.05, poll_interval=0.01))
    assert exc_info.value.job_id == "job-slow"


@respx.mock
@pytest.mark.asyncio
async def test_poll_job_failed_status():
    respx.get(f"{BASE}/api/v1/jobs/job-fail").mock(
        return_value=httpx.Response(200, json={
            "job_id": "job-fail", "status": "failed", "error": "provider error"
        })
    )
    async with _client() as c:
        job = await c.poll_job("job-fail")
    assert job.status == "failed"
    assert job.error == "provider error"


# ── review_pr ─────────────────────────────────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_review_pr_submits_with_pr_review_task():
    captured = {}

    def _capture(request):
        captured["body"] = request.content
        return httpx.Response(202, json={"job_id": "pr-job-1"})

    respx.post(f"{BASE}/api/v1/inference").mock(side_effect=_capture)
    async with _client() as c:
        job_id = await c.review_pr(ReviewPROptions(
            diff_url="https://github.com/org/repo/pull/42.diff",
            team_id="platform",
            user_id="alice",
        ))
    assert job_id == "pr-job-1"
    import json
    body = json.loads(captured["body"])
    assert body["task_type"] == "pr_review"
    assert body["team_id"] == "platform"


# ── error attributes ──────────────────────────────────────────────────────────

def test_error_hierarchy():
    from aegis_sdk.errors import AIPlatformError, AuthenticationError
    err = AuthenticationError("trace-001")
    assert isinstance(err, AIPlatformError)
    assert err.status_code == 401
    assert err.trace_id == "trace-001"


def test_rate_limit_error_has_retry_after():
    err = RateLimitError(retry_after=45)
    assert err.retry_after == 45
    assert err.status_code == 429


def test_job_timeout_error_has_job_id():
    err = JobTimeoutError("job-abc")
    assert err.job_id == "job-abc"
    assert err.status_code == 408
