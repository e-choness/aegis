/**
 * Aegis TypeScript SDK client.
 *
 * Usage:
 *   import { AegisClient } from "@aegis/sdk";
 *   const client = new AegisClient("http://localhost:8767", "aeg-...");
 *   const result = await client.createRun([{role: "user", content: "hi"}]);
 */

import {
  AuditResponseSchema,
  ChatCompletionResponseSchema,
  ResumeResponseSchema,
  RunCreateResponseSchema,
  RunStatusResponseSchema,
  type AuditRun,
  type ChatCompletionResponse,
  type Message,
  type ResumeResponse,
  type RunCreateResponse,
  type RunStatusResponse,
} from "./schemas.js";

export class AegisError extends Error {
  constructor(
    message: string,
    public readonly statusCode: number,
    public readonly body: unknown,
  ) {
    super(message);
    this.name = "AegisError";
  }
}

export class AegisClient {
  private readonly baseUrl: string;
  private readonly headers: Record<string, string>;

  constructor(baseUrl = "http://localhost:8767", apiKey = "") {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.headers = {
      "Content-Type": "application/json",
      ...(apiKey ? { Authorization: `Bearer ${apiKey}` } : {}),
    };
  }

  private async _fetch(path: string, init?: RequestInit): Promise<Response> {
    const resp = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      headers: { ...this.headers, ...(init?.headers ?? {}) },
    });
    if (!resp.ok) {
      const body = await resp.json().catch(() => null);
      throw new AegisError(`HTTP ${resp.status}`, resp.status, body);
    }
    return resp;
  }

  // ── /v1/runs ──────────────────────────────────────────────────────────────

  async createRun(
    messages: Message[],
    opts: { route?: string; background?: boolean; approvers?: string[] } = {},
  ): Promise<RunCreateResponse> {
    const resp = await this._fetch("/v1/runs", {
      method: "POST",
      body: JSON.stringify({
        messages,
        route: opts.route ?? "default",
        background: opts.background ?? false,
        approvers: opts.approvers ?? [],
      }),
    });
    return RunCreateResponseSchema.parse(await resp.json());
  }

  async getRun(runId: string): Promise<RunStatusResponse> {
    const resp = await this._fetch(`/v1/runs/${runId}`);
    return RunStatusResponseSchema.parse(await resp.json());
  }

  async resumeRun(runId: string, decision: "approved" | "denied"): Promise<ResumeResponse> {
    const resp = await this._fetch(`/v1/runs/${runId}/resume`, {
      method: "POST",
      body: JSON.stringify({ decision }),
    });
    return ResumeResponseSchema.parse(await resp.json());
  }

  // ── /v1/audit ─────────────────────────────────────────────────────────────

  async listRuns(opts: { principal?: string; route?: string; since?: string } = {}): Promise<AuditRun[]> {
    const params = new URLSearchParams();
    if (opts.principal) params.set("principal", opts.principal);
    if (opts.route) params.set("route", opts.route);
    if (opts.since) params.set("since", opts.since);
    const qs = params.size ? `?${params.toString()}` : "";
    const resp = await this._fetch(`/v1/audit${qs}`);
    return AuditResponseSchema.parse(await resp.json()).runs;
  }

  // ── /v1/chat/completions ──────────────────────────────────────────────────

  async chat(
    messages: Message[],
    opts: { model?: string } = {},
  ): Promise<ChatCompletionResponse> {
    const resp = await this._fetch("/v1/chat/completions", {
      method: "POST",
      body: JSON.stringify({ model: opts.model ?? "default", messages, stream: false }),
    });
    return ChatCompletionResponseSchema.parse(await resp.json());
  }

  /**
   * Stream a chat completion as an AsyncIterable of parsed SSE chunk objects.
   * Each yielded value is the raw parsed JSON from a `data:` event.
   */
  async *streamChat(
    messages: Message[],
    opts: { model?: string } = {},
  ): AsyncIterable<Record<string, unknown>> {
    const resp = await this._fetch("/v1/chat/completions", {
      method: "POST",
      body: JSON.stringify({ model: opts.model ?? "default", messages, stream: true }),
    });
    if (!resp.body) return;
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const data = line.slice(6).trim();
          if (data === "[DONE]") return;
          yield JSON.parse(data) as Record<string, unknown>;
        }
      }
    }
  }
}
