# LangServe Integration Guide

This guide shows how to integrate with Aegis Gateway's LangServe API surface from Python, TypeScript, and other environments.

---

## Table of Contents

1. [Python Integration](#python-integration)
2. [TypeScript Integration](#typescript-integration)
3. [cURL Examples](#curl-examples)
4. [Schema-Driven Code Generation](#schema-driven-code-generation)
5. [Error Handling](#error-handling)
6. [Performance Considerations](#performance-considerations)

---

## Python Integration

### Using LangServe RemoteRunnable

The easiest way to integrate with Aegis is via LangServe's `RemoteRunnable`:

```python
from langserve import RemoteRunnable

# Create a remote reference to the inference Runnable
runnable = RemoteRunnable("http://localhost:8000/api/v1/runnables/inference")

# Single invocation
result = runnable.invoke({
    "prompt": "Explain this Python function",
    "task_type": "code_explanation",
    "team_id": "platform",
    "user_id": "alice",
})

print(result["output"])
print(f"Cost: ${result['metadata']['cost_usd']}")
print(f"Model: {result['metadata']['model_alias']}")
```

### Batch Processing

```python
# Process multiple prompts in parallel
results = runnable.batch([
    {
        "prompt": "Review this code",
        "task_type": "pr_review",
        "team_id": "platform",
        "user_id": "alice",
    },
    {
        "prompt": "Find security issues",
        "task_type": "security_audit",
        "team_id": "platform",
        "user_id": "bob",
    },
    {
        "prompt": "Summarize this commit",
        "task_type": "commit_summary",
        "team_id": "platform",
        "user_id": "charlie",
    },
])

for result in results:
    print(f"Output: {result['output']}")
    print(f"Cost: ${result['metadata']['cost_usd']}")
    print()
```

### Streaming Responses

```python
# Stream tokens in real-time
for chunk in runnable.stream({
    "prompt": "Write a function to calculate fibonacci",
    "task_type": "code_generation",
    "team_id": "platform",
    "user_id": "alice",
}):
    if "token" in chunk:
        print(chunk["token"], end="", flush=True)
    elif "output" in chunk:
        print(f"\n\nFinal output: {chunk['output']}")
```

### Async Integration

```python
import asyncio
from langserve import RemoteRunnable

async def main():
    runnable = RemoteRunnable("http://localhost:8000/api/v1/runnables/inference")
    
    # Async single invocation
    result = await runnable.ainvoke({
        "prompt": "Explain async/await",
        "task_type": "code_explanation",
        "team_id": "platform",
        "user_id": "alice",
    })
    
    print(result["output"])

asyncio.run(main())
```

### Schema Discovery

```python
# Get schema to validate requests before sending
schema = runnable.get_schema()

print("Input schema:")
print(schema.input_schema)

print("\nOutput schema:")
print(schema.output_schema)

# Validate input
from pydantic import ValidationError
try:
    validated = schema.input_schema.parse_obj({
        "prompt": "Test",
        "task_type": "simple_qa",
        "team_id": "platform",
        # user_id missing - validation will fail
    })
except ValidationError as e:
    print(f"Validation error: {e}")
```

### Cost Tracking

```python
total_cost = 0.0

results = runnable.batch([...])

for result in results:
    cost = result['metadata']['cost_usd']
    total_cost += cost
    print(f"Invocation cost: ${cost}")

print(f"Total batch cost: ${total_cost}")
```

### Error Handling

```python
from httpx import HTTPStatusError

try:
    result = runnable.invoke({
        "prompt": "Test",
        "task_type": "simple_qa",
        "team_id": "overspent-team",  # Budget may be exceeded
        "user_id": "alice",
    })
except HTTPStatusError as e:
    if e.response.status_code == 429:
        print("Budget exceeded for team")
    elif e.response.status_code == 404:
        print("Runnable not found")
    else:
        print(f"Error: {e.response.json()}")
```

---

## TypeScript Integration

### Using httpx/fetch

```typescript
interface InferenceInput {
  prompt: string;
  task_type: string;
  team_id: string;
  user_id: string;
  complexity?: "low" | "medium" | "high";
  trace_id?: string;
}

interface InferenceOutput {
  output: string | null;
  metadata: {
    job_id: string;
    status: "completed" | "failed";
    model_alias: string;
    provider: string;
    tier: number;
    cost_usd: number;
    data_class: string;
    error?: string;
    latency_ms: number;
  };
}

async function invokeInference(input: InferenceInput): Promise<InferenceOutput> {
  const response = await fetch(
    "http://localhost:8000/api/v1/runnables/inference/invoke",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        input,
        config: { metadata: { trace_id: input.trace_id } },
      }),
    }
  );

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
  }

  return response.json();
}

// Usage
const result = await invokeInference({
  prompt: "Review this TypeScript code",
  task_type: "pr_review",
  team_id: "platform",
  user_id: "alice",
});

console.log(result.output);
console.log(`Cost: $${result.metadata.cost_usd}`);
```

### Batch Processing

```typescript
async function batchInference(inputs: InferenceInput[]): Promise<InferenceOutput[]> {
  const response = await fetch(
    "http://localhost:8000/api/v1/runnables/inference/batch",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        inputs,
        config: {},
      }),
    }
  );

  const result = await response.json();
  return result.outputs;
}

// Usage
const inputs: InferenceInput[] = [
  {
    prompt: "Commit message: Add user auth",
    task_type: "commit_summary",
    team_id: "platform",
    user_id: "alice",
  },
  {
    prompt: "Code review PR #123",
    task_type: "pr_review",
    team_id: "platform",
    user_id: "bob",
  },
];

const results = await batchInference(inputs);
results.forEach((result, i) => {
  console.log(`[${i}] Output: ${result.output}`);
  console.log(`     Cost: $${result.metadata.cost_usd}`);
});
```

### Streaming

```typescript
async function* streamInference(
  input: InferenceInput
): AsyncGenerator<string | InferenceOutput> {
  const query = new URLSearchParams({
    input_json: JSON.stringify(input),
  });

  const response = await fetch(
    `http://localhost:8000/api/v1/runnables/inference/stream?${query}`,
    { method: "GET" }
  );

  const reader = response.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.startsWith("event:")) {
        const event = line.replace("event:", "").trim();
        if (event === "token") {
          // Next line will be data
        }
      } else if (line.startsWith("data:")) {
        const data = JSON.parse(line.replace("data:", ""));
        yield data;
      }
    }
  }
}

// Usage
const input: InferenceInput = {
  prompt: "Explain quantum computing in simple terms",
  task_type: "code_explanation",
  team_id: "platform",
  user_id: "alice",
};

for await (const event of streamInference(input)) {
  if (event.token) {
    process.stdout.write(event.token);
  } else if (event.output) {
    console.log(`\n\nFinal cost: $${event.metadata.cost_usd}`);
  }
}
```

---

## cURL Examples

### List Runnables

```bash
curl http://localhost:8000/api/v1/runnables
```

### Get Schema

```bash
curl http://localhost:8000/api/v1/runnables/inference/schema
```

### Single Invocation

```bash
curl -X POST http://localhost:8000/api/v1/runnables/inference/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "prompt": "Summarize: The quick brown fox jumps over the lazy dog",
      "task_type": "simple_qa",
      "team_id": "platform",
      "user_id": "alice",
      "trace_id": "my-trace-001"
    },
    "config": {
      "metadata": {"trace_id": "my-trace-001"}
    }
  }' | jq
```

### Batch Invocation

```bash
curl -X POST http://localhost:8000/api/v1/runnables/inference/batch \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": [
      {"prompt": "P1", "task_type": "simple_qa", "team_id": "t1", "user_id": "u1"},
      {"prompt": "P2", "task_type": "simple_qa", "team_id": "t1", "user_id": "u2"}
    ],
    "config": {}
  }' | jq
```

### Stream Response

```bash
INPUT='{"prompt":"Hello world","task_type":"simple_qa","team_id":"t1","user_id":"u1"}'
ENCODED=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$INPUT'))")

curl "http://localhost:8000/api/v1/runnables/inference/stream?input_json=$ENCODED" \
  -H "Accept: text/event-stream"
```

---

## Schema-Driven Code Generation

### Using Pydantic

```python
from pydantic import BaseModel, ValidationError
from typing import Optional

# Get schema from remote
import httpx
schema_url = "http://localhost:8000/api/v1/runnables/inference/schema"
schema = httpx.get(schema_url).json()

# Generate Pydantic models from schema
# Option 1: Use datamodel-code-generator
# pydantic-codegen --input schema.json --output models.py

# Option 2: Define manually based on schema
class InferenceInput(BaseModel):
    prompt: str
    task_type: str
    team_id: str
    user_id: str
    complexity: Optional[str] = "medium"
    trace_id: Optional[str] = None

# Validate before sending
try:
    validated = InferenceInput(**user_input)
except ValidationError as e:
    print(f"Invalid input: {e}")
```

### Using JSONSchema

```javascript
// Generate TypeScript types from schema
const schema = await fetch("http://localhost:8000/api/v1/runnables/inference/schema").then(r => r.json());

// Use json-schema-to-typescript
// npm install json-schema-to-typescript
// json2ts schema.json > types.ts

import { InferenceInput, InferenceOutput } from "./types";

const input: InferenceInput = {
  prompt: "Test",
  task_type: "simple_qa",
  team_id: "platform",
  user_id: "alice",
};
```

---

## Error Handling

### HTTP Errors

| Status | Meaning | Example |
|--------|---------|---------|
| `400` | Invalid input | Missing required field |
| `404` | Runnable not found | Unknown runnable name |
| `429` | Budget exceeded | Team over monthly cap |
| `500` | Internal error | Unexpected server error |
| `503` | Service unavailable | All providers down |

### Python Error Handling

```python
from httpx import HTTPStatusError

try:
    result = runnable.invoke({...})
except HTTPStatusError as e:
    error_detail = e.response.json()
    print(f"Error: {error_detail['detail']}")
    
    if e.response.status_code == 429:
        # Budget exceeded
        print("Please wait until next billing period")
    elif e.response.status_code == 404:
        # Runnable not found
        print("Available runnables:", runnable.list())
    else:
        # Other error
        print(f"Status: {e.response.status_code}")
```

### TypeScript Error Handling

```typescript
try {
  const result = await invokeInference(input);
} catch (error) {
  if (error instanceof Error) {
    if (error.message.includes("429")) {
      console.error("Budget exceeded");
    } else if (error.message.includes("404")) {
      console.error("Runnable not found");
    } else {
      console.error(`Error: ${error.message}`);
    }
  }
}
```

---

## Performance Considerations

### Timeouts

```python
# Set reasonable timeouts
from httpx import Client

client = Client(timeout=60.0)  # 60 second timeout
runnable = RemoteRunnable("http://localhost:8000/...", client=client)
```

### Connection Pooling

```python
# Reuse HTTP connections for better performance
from httpx import Client

client = Client()
runnable = RemoteRunnable("http://localhost:8000/...", client=client)

# Use multiple times
for i in range(100):
    result = runnable.invoke({...})
```

### Async Parallelization

```python
import asyncio
from langserve import RemoteRunnable

async def process_batch_parallel(inputs):
    runnable = RemoteRunnable("http://localhost:8000/api/v1/runnables/inference")
    
    tasks = [runnable.ainvoke(inp) for inp in inputs]
    results = await asyncio.gather(*tasks)
    
    return results

# Process 100 requests in parallel
inputs = [{"prompt": f"P{i}", ...} for i in range(100)]
results = asyncio.run(process_batch_parallel(inputs))
```

### Cost Optimization

```python
# Use task_type to route to cheaper models
# "low" complexity → Haiku (cheaper)
# "medium" → Sonnet
# "high" → Opus

results = runnable.batch([
    {
        "prompt": "Summarize: ...",
        "task_type": "commit_summary",  # Usually simple
        "team_id": "platform",
        "user_id": "alice",
        "complexity": "low",  # Use cheaper model
    },
    {
        "prompt": "Architect: ...",
        "task_type": "architecture_review",  # Complex task
        "team_id": "platform",
        "user_id": "bob",
        "complexity": "high",  # Use Opus
    },
])

total_cost = sum(r["metadata"]["cost_usd"] for r in results)
print(f"Total cost: ${total_cost}")
```

### Streaming for Large Responses

```python
# For large generations, stream instead of waiting for entire response
total_tokens = 0

for chunk in runnable.stream(input):
    if "token" in chunk:
        total_tokens += 1
        if total_tokens % 10 == 0:
            print(f"... {total_tokens} tokens so far")

print(f"Total tokens: {total_tokens}")
```

---

## Troubleshooting

### Connection Refused

```
Error: Connection refused
```

**Solution:** Ensure Docker services are running:
```bash
docker-compose ps
# Should show gateway running on port 8000
```

### Schema Not Found

```
Error: 404 Runnable 'inference' not found
```

**Solution:** Check available runnables:
```bash
curl http://localhost:8000/api/v1/runnables
```

### Budget Exceeded

```
Error: 429 Budget exceeded
```

**Solution:** Check budget status or reduce team allocation. No retries will help.

### Timeout

```
Error: Request timeout after 30s
```

**Solution:** Increase timeout or use streaming for long-running requests.

---

## See Also

- [LangServe Documentation](https://github.com/langchain-ai/langserve)
- [LangChain Python Docs](https://python.langchain.com/)
- [Aegis API Reference](langserve-api.md)
