from __future__ import annotations


class AIPlatformError(Exception):
    def __init__(self, message: str, status_code: int, trace_id: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.trace_id = trace_id


class AuthenticationError(AIPlatformError):
    def __init__(self, trace_id: str | None = None) -> None:
        super().__init__("Authentication failed", 401, trace_id)


class RateLimitError(AIPlatformError):
    def __init__(self, retry_after: int, trace_id: str | None = None) -> None:
        super().__init__(f"Rate limit exceeded. Retry after {retry_after}s", 429, trace_id)
        self.retry_after = retry_after


class BudgetExceededError(AIPlatformError):
    def __init__(self, trace_id: str | None = None) -> None:
        super().__init__("Team budget exceeded", 402, trace_id)


class DataResidencyError(AIPlatformError):
    def __init__(self, trace_id: str | None = None) -> None:
        super().__init__("RESTRICTED data cannot be sent to cloud providers", 451, trace_id)


class ModelUnavailableError(AIPlatformError):
    def __init__(self, trace_id: str | None = None) -> None:
        super().__init__("No model available to handle this request", 503, trace_id)


class JobTimeoutError(AIPlatformError):
    def __init__(self, job_id: str) -> None:
        super().__init__(f"Job {job_id} did not complete within the timeout", 408)
        self.job_id = job_id
