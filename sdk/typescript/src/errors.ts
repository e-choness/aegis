export class AIPlatformError extends Error {
  constructor(
    message: string,
    public readonly statusCode: number,
    public readonly traceId?: string,
  ) {
    super(message);
    this.name = this.constructor.name;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export class AuthenticationError extends AIPlatformError {
  constructor(traceId?: string) {
    super("Authentication failed", 401, traceId);
  }
}

export class RateLimitError extends AIPlatformError {
  constructor(
    public readonly retryAfter: number,
    traceId?: string,
  ) {
    super(`Rate limit exceeded. Retry after ${retryAfter}s`, 429, traceId);
  }
}

export class BudgetExceededError extends AIPlatformError {
  constructor(traceId?: string) {
    super("Team budget exceeded", 402, traceId);
  }
}

export class DataResidencyError extends AIPlatformError {
  constructor(traceId?: string) {
    super("RESTRICTED data cannot be sent to cloud providers", 451, traceId);
  }
}

export class ModelUnavailableError extends AIPlatformError {
  constructor(traceId?: string) {
    super("No model available to handle this request", 503, traceId);
  }
}

export class JobTimeoutError extends AIPlatformError {
  constructor(public readonly jobId: string) {
    super(`Job ${jobId} did not complete within the timeout`, 408);
  }
}
