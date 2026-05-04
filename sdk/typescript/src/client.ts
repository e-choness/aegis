import {
  AIPlatformError, AuthenticationError, BudgetExceededError,
  DataResidencyError, JobTimeoutError, ModelUnavailableError, RateLimitError,
} from "./errors";
import type { InferenceRequest, JobResult, PollOptions, ReviewPROptions } from "./types";

export class AIPlatformClient {
  private readonly baseUrl: string;
  private readonly headers: Record<string, string>;

  constructor(options: { ssoToken: string; baseUrl?: string }) {
    this.baseUrl = (options.baseUrl ?? "http://localhost:8000").replace(/\/$/, "");
    this.headers = {
      "Content-Type": "application/json",
      Authorization: `Bearer ${options.ssoToken}`,
    };
  }

  async submitInference(request: InferenceRequest): Promise<string> {
    const response = await fetch(`${this.baseUrl}/api/v1/inference`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify(request),
    });
    this._assertOk(response);
    const data = (await response.json()) as { job_id: string };
    return data.job_id;
  }

  async reviewPR(options: ReviewPROptions): Promise<string> {
    return this.submitInference({
      prompt: options.diffUrl,
      task_type: "pr_review",
      team_id: options.teamId,
      user_id: options.userId,
      trace_id: options.traceId,
    });
  }

  async pollJob(jobId: string, options: PollOptions = {}): Promise<JobResult> {
    const timeout = options.timeout ?? 90_000;
    const interval = options.pollInterval ?? 2_000;
    const deadline = Date.now() + timeout;

    while (Date.now() < deadline) {
      const response = await fetch(`${this.baseUrl}/api/v1/jobs/${jobId}`, {
        headers: this.headers,
      });
      this._assertOk(response);

      const job = (await response.json()) as JobResult;
      if (job.status === "completed" || job.status === "failed") {
        return job;
      }
      await this._sleep(interval);
    }

    throw new JobTimeoutError(jobId);
  }

  private _assertOk(response: Response): void {
    if (response.ok) return;
    const traceId = response.headers.get("x-trace-id") ?? undefined;
    switch (response.status) {
      case 401: throw new AuthenticationError(traceId);
      case 402: throw new BudgetExceededError(traceId);
      case 429: throw new RateLimitError(
        parseInt(response.headers.get("retry-after") ?? "60", 10),
        traceId,
      );
      case 451: throw new DataResidencyError(traceId);
      case 503: throw new ModelUnavailableError(traceId);
      default:  throw new AIPlatformError(`HTTP ${response.status}`, response.status, traceId);
    }
  }

  private _sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}
