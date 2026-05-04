import { AIPlatformClient } from "../src/client";
import {
  AIPlatformError,
  AuthenticationError,
  BudgetExceededError,
  DataResidencyError,
  JobTimeoutError,
  ModelUnavailableError,
  RateLimitError,
} from "../src/errors";

// Mock the global fetch
const mockFetch = jest.fn();
global.fetch = mockFetch;

function makeResponse(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: (k: string) => headers[k.toLowerCase()] ?? null } as unknown as Headers,
    json: async () => body,
  } as unknown as Response;
}

describe("error hierarchy", () => {
  it("RateLimitError carries retryAfter and inherits AIPlatformError", () => {
    const err = new RateLimitError(45);
    expect(err.retryAfter).toBe(45);
    expect(err.statusCode).toBe(429);
    expect(err).toBeInstanceOf(AIPlatformError);
    expect(err).toBeInstanceOf(Error);
  });

  it("BudgetExceededError has statusCode 402", () => {
    const err = new BudgetExceededError("trace-1");
    expect(err.statusCode).toBe(402);
    expect(err.traceId).toBe("trace-1");
  });

  it("DataResidencyError has statusCode 451", () => {
    expect(new DataResidencyError().statusCode).toBe(451);
  });

  it("JobTimeoutError carries jobId", () => {
    const err = new JobTimeoutError("job-abc");
    expect(err.jobId).toBe("job-abc");
    expect(err.statusCode).toBe(408);
  });
});

describe("AIPlatformClient", () => {
  beforeEach(() => mockFetch.mockReset());

  const client = new AIPlatformClient({ ssoToken: "test-token" });

  describe("submitInference", () => {
    it("returns job_id on 202", async () => {
      mockFetch.mockResolvedValueOnce(makeResponse(202, { job_id: "abc-123", status: "queued" }));
      const jobId = await client.submitInference({
        prompt: "summarise this diff",
        task_type: "pr_review",
        team_id: "team-platform",
        user_id: "u1",
      });
      expect(jobId).toBe("abc-123");
    });

    it("throws AuthenticationError on 401", async () => {
      mockFetch.mockResolvedValueOnce(makeResponse(401, {}));
      await expect(
        client.submitInference({ prompt: "test", task_type: "general", team_id: "t", user_id: "u" })
      ).rejects.toThrow(AuthenticationError);
    });

    it("throws BudgetExceededError on 402", async () => {
      mockFetch.mockResolvedValueOnce(makeResponse(402, {}));
      await expect(
        client.submitInference({ prompt: "test", task_type: "general", team_id: "t", user_id: "u" })
      ).rejects.toThrow(BudgetExceededError);
    });

    it("throws RateLimitError with retryAfter from header on 429", async () => {
      mockFetch.mockResolvedValueOnce(makeResponse(429, {}, { "retry-after": "30" }));
      const err = await client
        .submitInference({ prompt: "test", task_type: "general", team_id: "t", user_id: "u" })
        .catch((e) => e);
      expect(err).toBeInstanceOf(RateLimitError);
      expect((err as RateLimitError).retryAfter).toBe(30);
    });

    it("throws DataResidencyError on 451", async () => {
      mockFetch.mockResolvedValueOnce(makeResponse(451, {}));
      await expect(
        client.submitInference({ prompt: "test", task_type: "general", team_id: "t", user_id: "u" })
      ).rejects.toThrow(DataResidencyError);
    });

    it("throws ModelUnavailableError on 503", async () => {
      mockFetch.mockResolvedValueOnce(makeResponse(503, {}));
      await expect(
        client.submitInference({ prompt: "test", task_type: "general", team_id: "t", user_id: "u" })
      ).rejects.toThrow(ModelUnavailableError);
    });
  });

  describe("pollJob", () => {
    it("resolves immediately when job is already completed", async () => {
      mockFetch.mockResolvedValueOnce(
        makeResponse(200, { job_id: "j1", status: "completed", content: "LGTM" })
      );
      const result = await client.pollJob("j1");
      expect(result.status).toBe("completed");
      expect(result.content).toBe("LGTM");
    });

    it("resolves on second poll when job transitions to completed", async () => {
      mockFetch
        .mockResolvedValueOnce(makeResponse(200, { job_id: "j2", status: "running" }))
        .mockResolvedValueOnce(makeResponse(200, { job_id: "j2", status: "completed", content: "Done" }));
      const result = await client.pollJob("j2", { pollInterval: 10 });
      expect(result.status).toBe("completed");
      expect(mockFetch).toHaveBeenCalledTimes(2);
    });

    it("throws JobTimeoutError when job never completes within timeout", async () => {
      mockFetch.mockResolvedValue(makeResponse(200, { job_id: "j3", status: "running" }));
      await expect(client.pollJob("j3", { timeout: 50, pollInterval: 10 })).rejects.toThrow(
        JobTimeoutError
      );
    });

    it("resolves with failed status", async () => {
      mockFetch.mockResolvedValueOnce(
        makeResponse(200, { job_id: "j4", status: "failed", error: "budget exceeded" })
      );
      const result = await client.pollJob("j4");
      expect(result.status).toBe("failed");
      expect(result.error).toBe("budget exceeded");
    });
  });
});
