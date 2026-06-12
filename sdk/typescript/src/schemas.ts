/**
 * Zod schemas for Aegis v2 API request and response shapes.
 */

import { z } from "zod";

// ---------------------------------------------------------------------------
// Shared primitives
// ---------------------------------------------------------------------------

export const MessageSchema = z.object({
  role: z.string(),
  content: z.string(),
});

// ---------------------------------------------------------------------------
// /v1/runs
// ---------------------------------------------------------------------------

export const RunCreateRequestSchema = z.object({
  messages: z.array(MessageSchema),
  route: z.string().default("default"),
  approvers: z.array(z.string()).default([]),
  background: z.boolean().default(false),
});

export const RunCreateResponseSchema = z.object({
  run_id: z.string(),
  response: z.string().nullable(),
  principal_id: z.string(),
  events: z.array(z.record(z.unknown())),
  status: z.string(),
});

export const RunStatusResponseSchema = z.object({
  run_id: z.string(),
  route: z.string(),
  principal_id: z.string(),
  status: z.string(),
  approvers: z.array(z.string()),
});

export const ResumeResponseSchema = z.object({
  run_id: z.string(),
  status: z.string(),
  response: z.string().nullable(),
  events: z.array(z.record(z.unknown())),
});

// ---------------------------------------------------------------------------
// /v1/audit
// ---------------------------------------------------------------------------

export const AuditRunSchema = z.object({
  run_id: z.string(),
  route: z.string(),
  principal_id: z.string(),
  status: z.string(),
  created_at: z.string(),
});

export const AuditResponseSchema = z.object({
  runs: z.array(AuditRunSchema),
});

// ---------------------------------------------------------------------------
// /v1/chat/completions
// ---------------------------------------------------------------------------

export const ChatCompletionRequestSchema = z.object({
  model: z.string().default("default"),
  messages: z.array(MessageSchema),
  stream: z.boolean().default(false),
});

export const ChatChoiceSchema = z.object({
  index: z.number(),
  message: MessageSchema,
  finish_reason: z.string(),
});

export const ChatCompletionResponseSchema = z.object({
  id: z.string(),
  object: z.string(),
  created: z.number(),
  model: z.string(),
  choices: z.array(ChatChoiceSchema),
  usage: z.object({
    prompt_tokens: z.number(),
    completion_tokens: z.number(),
    total_tokens: z.number(),
  }),
});

// ---------------------------------------------------------------------------
// TypeScript types inferred from schemas
// ---------------------------------------------------------------------------

export type Message = z.infer<typeof MessageSchema>;
export type RunCreateRequest = z.infer<typeof RunCreateRequestSchema>;
export type RunCreateResponse = z.infer<typeof RunCreateResponseSchema>;
export type RunStatusResponse = z.infer<typeof RunStatusResponseSchema>;
export type ResumeResponse = z.infer<typeof ResumeResponseSchema>;
export type AuditRun = z.infer<typeof AuditRunSchema>;
export type ChatCompletionRequest = z.infer<typeof ChatCompletionRequestSchema>;
export type ChatCompletionResponse = z.infer<typeof ChatCompletionResponseSchema>;
