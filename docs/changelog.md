# Changelog

All notable changes to this project will be documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/).
Edit the Unreleased section as you go; on release it becomes the version's
section, and `scripts/release.py notes` turns it into the GitHub Release notes.
`uv run git-cliff --unreleased` can draft entries from conventional commits.

## [Unreleased]

### Security

- Streamed `/v1/chat/completions` requests on true-streaming routes skipped every ingress node (PII masking, residency, budgets) and were never recorded. Ingress now always runs first, pauses stay resumable, and egress nodes that don't declare `stream_capability` make a route buffer.
- `aegis serve` refuses to start when `tool_call` / `tool_result` stages are configured, instead of silently not enforcing them (`AEG-POL-004` in `aegis policy lint`).

### Fixed

- `anthropic` and `openai_compatible` providers could not be built from `aegis.yaml` (missing `name`, API key passed as plain text); `openai_compatible` now pins the OpenAI protocol so self-hosted model names work.
- Budgets never accumulated spend: the pack now adds an egress recorder (`egress: [budget]`).
- Chat runs are written to the run store and ledger with their real status and events (previously always `completed` with no events); blocked/paused chats return `finish_reason: content_filter`.
- `docker-compose.demo.yml` and `scripts/demo.sh` used the removed `aegis dev` command.
- A paused run lost the verdict that paused it (LangGraph's interrupt discarded the node's events), so `aegis explain`, the ledger and the approvals UI couldn't show *why* a run was waiting.
- `ChromaVectorStore.query()` ignored the query vector and returned documents in insertion order; it now does a similarity search. Namespaces shorter than three characters (e.g. `hr`) no longer crash Chroma — collections are named `aegis-<namespace>`.
- Demo rate limiting: the "hard cap" was a lifetime counter (the demo died after 100 requests), every visitor behind a proxy shared one quota, and the showcase page's own polling consumed it. It now limits pipeline runs per visitor (`X-Forwarded-For`) with a rolling hourly cap.
- The showcase page could only use the `default` route and never showed paused runs in its approval queue.

### Changed

- `aegis serve` persists runs to SQLite (`--runs-db`, default `aegis_runs.db`), so paused runs stay resumable and `aegis explain` keeps working across restarts.
- Pack factories import `GuardrailConfig` / `PackNodes` from the new public `aegis_core.packs` module; the import-linter contract now passes and runs in CI.
- One version for every package: `__version__` comes from package metadata, internal dependencies are pinned exactly, and `scripts/release.py bump` updates everything.
- Removed duplicate RAG helpers (`rag.chunking`, `rag.chroma_store`, `rag.pgvector_store`) in favour of `TextChunker`, `ChromaVectorStore` and `PgVectorStore`.
- Examples rewritten to exercise the real packs (PII, MCP tool guards, governed RAG, residency); the duplicate `examples/scenarios/` copies are gone and the approval scenario runs with `scripts/approval-scenario.sh`.
- The Hugging Face demo is defined in `deploy/huggingface/` and installs the released packages from PyPI; the old sync scripts, `Dockerfile.hf` and container-repair scripts are removed.

### Added

- Provider plugins: any non-built-in `type:` resolves through the `aegis.providers` entry-point group.
- `GET /v1/models` lists routes for OpenAI-compatible UIs.
- `aegis serve --demo` for public, no-auth demos.
- `aegis policy lint` checks endpoint-encoded regions against `residency.region` (`AEG-POL-005`).
- Release automation (`.github/workflows/release.yml`): tag-triggered PyPI publishing with Trusted Publishing, GitHub Releases from this changelog, and Hugging Face Space deployment. Every package now has a PyPI description, classifiers and documentation/changelog links.
- Docs moved to VitePress; animated SVG banners and README terminal demo.
- OSFI E-23 compliance report — `run_evidence` ledger emission on every chat completion, `GET /v1/audit/report` endpoint (inventory + run_stats + chain_length), `aegis report summary` CLI command, SDK `audit_report()` method.

## [0.1.0] - 2026-06-21

### Build Steps

- (**01**) Repository bootstrap — uv workspace, Docker dev env, CI, empty-but-green packages
- (**02**) Kernel — typed config + secrets
- (**03**) Kernel — plugin registry + hooks
- (**04**) Providers — ModelProvider protocol, LiteLLM wrapper, profiles, provider CLI
- (**05**) Pipeline runtime — RunState, Verdict, PipelineNode, assembler, executor, aegis chat
- (**06**) Serving + identity — FastAPI app, auth, virtual keys, /v1/runs, /v1/chat/completions
- (**07**) Guardrail core + policy lint
- (**08**) Streaming — SSE endpoints, capability negotiation, hold-back finalize, AEG-POL-003 lint
- (**09**) Hitl — checkpointed pause/resume, approve/deny, AEG-AUTH-003
- (**10**) Policy packs wave 1 — PII + LLM Guard adapters, import-linter
- (**11**) MCP — governed tool-calling client and server
- (**12**) Rag — retrieval node, governed context injection, [rag] extra
- (**13**) Policy packs wave 2 — classification, residency, budgets
- (**14**) Background runs + observability
- (**15**) SDKs + OpenAPI artifact
- (**16**) DX hardening — scaffold, doctor, init, error sweep
- (**17**) Showcase — demo gallery, approvals UI, demo.sh CI gate
- (**17**) Showcase
- (**17**) Fix example 03 (ToolResult removed, event_type) and example 05 (labels not metadata)
- (**18**) Documentation suite + repo front matter
- (**19**) README generation — banner, badges, mermaid diagrams, quick start, links
- (**20**) Demo safety rails — per-IP rate limit, hard cap, budget guard
- (**21**) Examples runnable + documented
- (**22**) Wire demo + examples into CI
- (**23**) Final pass + first release tag



