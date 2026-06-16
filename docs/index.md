# Aegis AI Gateway

[![CI](https://github.com/aegis-ai/aegis/actions/workflows/ci.yml/badge.svg?style=flat-square)](https://github.com/aegis-ai/aegis/actions/workflows/ci.yml)
[![Docs](https://github.com/e-choness/aegis/actions/workflows/docs.yml/badge.svg?style=flat-square)](https://e-choness.github.io/aegis/)
[![PyPI](https://img.shields.io/pypi/v/aegis-ai?style=flat-square)](https://pypi.org/project/aegis-ai/)
[![Python](https://img.shields.io/pypi/pyversions/aegis-ai?style=flat-square)](https://pypi.org/project/aegis-ai/)
[![License](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](https://github.com/aegis-ai/aegis/blob/main/LICENSE)
[![Code style: ruff + pyright](https://img.shields.io/badge/code%20style-ruff%20%2B%20pyright-black?style=flat-square)](https://github.com/aegis-ai/aegis)

An open-source, plugin-first AI gateway framework. A small kernel plus seven plugin contracts puts a governed, observable, provider-agnostic pipeline between applications and LLM providers. Every flagship feature — data classification, residency enforcement, PII masking, budgets — is built on the same public contracts third-party developers use. Self-hosted, CLI-first, single-tenant-by-design.

**Features:**

- Provider-agnostic: LiteLLM backend, any OpenAI-compatible endpoint, or your own `ModelProvider`
- Four-verdict guardrail system: allow, block, sanitize, require_approval
- Human-in-the-loop (HITL) with LangGraph checkpointed interrupts
- OpenAI-compatible `/v1/chat/completions` — drop-in for any OpenAI client
- True streaming with capability negotiation (buffered fallback, OpenAI SSE wire)
- MCP tool governance: pre- and post-call guards on every tool invocation
- RAG with governed context injection
- Policy packs: PII masking, classification, residency, budgets
- First-party Python + TypeScript SDKs

## Architecture

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'background': 'transparent', 'primaryColor': '#3f51b5', 'primaryTextColor': '#ffffff', 'primaryBorderColor': '#283593', 'lineColor': '#7986cb', 'secondaryColor': '#3949ab', 'tertiaryColor': '#5c6bc0', 'clusterBkg': '#e8eaf6', 'clusterBorder': '#7986cb', 'edgeLabelBackground': '#e8eaf6', 'titleColor': '#1a237e', 'nodeTextColor': '#ffffff'}}}%%
flowchart TD
    subgraph IF[Interfaces]
        CLI[CLI · Typer + Rich]
        REST[REST API · native + OpenAI-compat]
        MCPS[MCP server]
        SDK[SDKs · Python + TypeScript]
    end
    AUTH[Auth middleware — Authenticator resolves Principal]
    subgraph PR[Pipeline runtime — LangGraph StateGraph]
        IN[Ingress guards] --> RX[Route + execute] --> EG[Egress guards]
    end
    subgraph K[Plugin kernel]
        REG[Plugin registry — entry points]
        CFG[Typed config + secret resolution]
        ASM[Per-route graph assembler]
        HK[Hooks + events — pluggy]
    end
    subgraph C[Seven plugin contracts]
        MP[ModelProvider] & GP[GuardrailProvider] & RG[VectorStore/Embedding]
        SP[SecretProvider] & TE[Telemetry exporter] & PN[PipelineNode] & AU[Authenticator]
    end
    subgraph PP[Optional policy packs — public contracts only]
        CL[Classification] & RES[Residency] & BUD[Budgets] & PII[PII mask]
    end
    IF --> AUTH --> PR --> K --> C --> PP
```

## Quick start

```bash
pip install aegis-ai
aegis init            # writes starter aegis.yaml
aegis dev             # localhost gateway, no auth, FakeProvider
```

Then point any OpenAI client at `http://localhost:8000/v1`:

```python
import openai

client = openai.OpenAI(base_url="http://localhost:8000/v1", api_key="demo")
response = client.chat.completions.create(
    model="default",
    messages=[{"role": "user", "content": "Hello, Aegis!"}],
)
print(response.choices[0].message.content)
```

See the [five-minute gateway tutorial](tutorials/five-minute-gateway.md) for a full walkthrough.

## Links

- [Examples gallery](https://github.com/aegis-ai/aegis/tree/main/examples)
- [Plugin authoring guide](tutorials/first-guardrail.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)
- [v1 legacy tag](https://github.com/aegis-ai/aegis/releases/tag/v1-legacy) — v1 users, start here
