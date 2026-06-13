/**
 * AegisClient unit tests — fetch layer mocked via vitest.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AegisClient, AegisError } from "../src/client.js";

// ---------------------------------------------------------------------------
// fetch mock helpers
// ---------------------------------------------------------------------------

function mockFetch(body: unknown, status = 200): void {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: status < 400,
      status,
      json: async () => body,
      body: null,
    }),
  );
}

function mockFetchError(status: number, body: unknown): void {
  mockFetch(body, status);
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// ---------------------------------------------------------------------------
// createRun
// ---------------------------------------------------------------------------

describe("AegisClient.createRun", () => {
  it("posts to /v1/runs and returns RunCreateResponse", async () => {
    const responseBody = {
      run_id: "r1",
      response: "hello",
      principal_id: "alice",
      events: [],
      status: "completed",
    };
    mockFetch(responseBody);

    const client = new AegisClient("http://test", "key");
    const result = await client.createRun([{ role: "user", content: "hi" }]);

    const fetchMock = vi.mocked(fetch);
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://test/v1/runs");
    expect(init.method).toBe("POST");
    expect(result.run_id).toBe("r1");
    expect(result.status).toBe("completed");
  });

  it("sends background=true when requested", async () => {
    mockFetch({ run_id: "r2", response: null, principal_id: "u", events: [], status: "pending" });

    const client = new AegisClient("http://test", "key");
    await client.createRun([{ role: "user", content: "hi" }], { background: true });

    const [, init] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
    const sent = JSON.parse(init.body as string) as { background: boolean };
    expect(sent.background).toBe(true);
  });

  it("throws AegisError on 401", async () => {
    mockFetchError(401, { detail: "Unauthorized" });
    const client = new AegisClient("http://test", "badkey");
    await expect(client.createRun([{ role: "user", content: "hi" }])).rejects.toThrow(AegisError);
  });
});

// ---------------------------------------------------------------------------
// getRun
// ---------------------------------------------------------------------------

describe("AegisClient.getRun", () => {
  it("calls GET /v1/runs/{id}", async () => {
    mockFetch({
      run_id: "r1",
      route: "default",
      principal_id: "alice",
      status: "completed",
      approvers: [],
    });

    const client = new AegisClient("http://test", "key");
    const result = await client.getRun("r1");

    const [url] = vi.mocked(fetch).mock.calls[0] as [string];
    expect(url).toBe("http://test/v1/runs/r1");
    expect(result.run_id).toBe("r1");
  });

  it("throws AegisError on 404", async () => {
    mockFetchError(404, { detail: "Not found" });
    const client = new AegisClient("http://test", "key");
    await expect(client.getRun("missing")).rejects.toThrow(AegisError);
  });
});

// ---------------------------------------------------------------------------
// resumeRun
// ---------------------------------------------------------------------------

describe("AegisClient.resumeRun", () => {
  it("posts decision to /v1/runs/{id}/resume", async () => {
    mockFetch({ run_id: "r1", status: "completed", response: "ok", events: [] });

    const client = new AegisClient("http://test", "key");
    const result = await client.resumeRun("r1", "approved");

    const [url, init] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://test/v1/runs/r1/resume");
    const body = JSON.parse(init.body as string) as { decision: string };
    expect(body.decision).toBe("approved");
    expect(result.status).toBe("completed");
  });
});

// ---------------------------------------------------------------------------
// listRuns
// ---------------------------------------------------------------------------

describe("AegisClient.listRuns", () => {
  it("calls GET /v1/audit", async () => {
    mockFetch({
      runs: [
        {
          run_id: "r1",
          route: "default",
          principal_id: "alice",
          status: "completed",
          created_at: "2026-01-01T00:00:00Z",
        },
      ],
    });

    const client = new AegisClient("http://test", "key");
    const runs = await client.listRuns();

    const [url] = vi.mocked(fetch).mock.calls[0] as [string];
    expect(url).toBe("http://test/v1/audit");
    expect(runs).toHaveLength(1);
    expect(runs[0].run_id).toBe("r1");
  });

  it("passes query parameters for filtering", async () => {
    mockFetch({ runs: [] });

    const client = new AegisClient("http://test", "key");
    await client.listRuns({ principal: "alice", route: "default" });

    const [url] = vi.mocked(fetch).mock.calls[0] as [string];
    expect(url).toContain("principal=alice");
    expect(url).toContain("route=default");
  });
});

// ---------------------------------------------------------------------------
// chat
// ---------------------------------------------------------------------------

describe("AegisClient.chat", () => {
  it("posts to /v1/chat/completions", async () => {
    mockFetch({
      id: "c1",
      object: "chat.completion",
      created: 0,
      model: "default",
      choices: [{ index: 0, message: { role: "assistant", content: "hi" }, finish_reason: "stop" }],
      usage: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2 },
    });

    const client = new AegisClient("http://test", "key");
    const result = await client.chat([{ role: "user", content: "hello" }]);

    const [url] = vi.mocked(fetch).mock.calls[0] as [string];
    expect(url).toBe("http://test/v1/chat/completions");
    expect(result.choices[0].message.content).toBe("hi");
  });
});

// ---------------------------------------------------------------------------
// AegisError
// ---------------------------------------------------------------------------

describe("AegisError", () => {
  it("carries statusCode and body", async () => {
    mockFetchError(403, { detail: "Forbidden" });
    const client = new AegisClient("http://test", "key");
    try {
      await client.getRun("r1");
    } catch (err) {
      expect(err).toBeInstanceOf(AegisError);
      const e = err as AegisError;
      expect(e.statusCode).toBe(403);
      expect((e.body as { detail: string }).detail).toBe("Forbidden");
    }
  });
});
