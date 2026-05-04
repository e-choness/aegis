export interface InferenceRequest {
  prompt: string;
  task_type?: string;
  team_id: string;
  user_id: string;
  complexity?: "low" | "medium" | "high";
  trace_id?: string;
}

export interface InferenceResponse {
  job_id: string;
  status: string;
  trace_id?: string;
}

export interface JobResult {
  job_id: string;
  status: "queued" | "running" | "completed" | "failed";
  content?: string;
  model_alias?: string;
  provider?: string;
  tier?: number;
  cost_usd?: number;
  data_classification?: string;
  error?: string;
}

export interface ReviewPROptions {
  diffUrl: string;
  teamId: string;
  userId: string;
  traceId?: string;
}

export interface PollOptions {
  /** Poll timeout in milliseconds. Default: 90_000 */
  timeout?: number;
  /** Interval between polls in milliseconds. Default: 2_000 */
  pollInterval?: number;
}
