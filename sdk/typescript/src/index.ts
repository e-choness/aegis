/**
 * Aegis v2 TypeScript SDK — public API.
 */

export { AegisClient, AegisError } from "./client.js";
export type {
  AuditRun,
  ChatCompletionRequest,
  ChatCompletionResponse,
  Message,
  ResumeResponse,
  RunCreateRequest,
  RunCreateResponse,
  RunStatusResponse,
} from "./schemas.js";
export {
  AuditResponseSchema,
  AuditRunSchema,
  ChatCompletionRequestSchema,
  ChatCompletionResponseSchema,
  MessageSchema,
  ResumeResponseSchema,
  RunCreateRequestSchema,
  RunCreateResponseSchema,
  RunStatusResponseSchema,
} from "./schemas.js";
