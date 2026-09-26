# Changelog

Notable changes to Aegis, newest first. Versions follow
[PEP 440](https://peps.python.org/pep-0440/) and every package in a release
shares one version. The format follows [Keep a Changelog](https://keepachangelog.com/).

Changes land under **Unreleased** as they merge; on release that section
becomes the version's entry and its GitHub Release notes.

## [Unreleased]

## [2.0.0a2] - 2026-09-26

### Changed

- Package versions come from git tags (`hatch-vcs`): pushing a tag such as
  `v2.0.0a3` releases every package as `2.0.0a3`, with no version bump commit.
  Dev checkouts report versions like `2.0.0a4.dev2`.

### Fixed

- The PII pack let Presidio pick its default spaCy model, `en_core_web_lg`,
  and download it (~560 MB) on the first request. That failed in read-only or
  non-root containers — every run on the Hugging Face demo returned 500 — and
  made the first request slow elsewhere. The pack now loads `en_core_web_sm`
  (configurable with `spacy_model:`), never downloads, and fails at startup
  with the install command if the model is missing.
- Overlapping PII detections now keep the most confident one, so a spaCy name
  guess can no longer swallow an adjacent email or card number.
- Releases publish `aegis-gateway` only after every component uploaded, so a
  failed upload can't leave an umbrella release pointing at missing packages.
- `UK_NINO` removed from the default PII entities: current Presidio has no
  recognizer for it.

## [2.0.0a1] - 2026-09-26

Everything since the first public alpha. Upgrading from 2.0.0a0? Read
**Breaking changes** first.

### Breaking changes

- **License is now AGPL-3.0-or-later** (was MIT). Self-hosting, modifying and
  commercial use are unaffected; if you distribute a modified Aegis, or let
  users reach a modified Aegis over a network, you must offer them its source.
  Plugins may use any AGPL-compatible license.
- **PII masking is more selective by default.** Only identifying entities are
  masked (names, contact details, account and government IDs). `DATE_TIME`,
  `URL`, `NRP`, `US_DRIVER_LICENSE` and region-specific IDs are now opt-in via
  `entities:` — add `DATE_TIME` back if you relied on dates of birth being masked.
- **Streaming routes buffer** when an egress node doesn't declare
  `stream_capability` (e.g. PII unmasking, budget recording), so those nodes
  see the whole response.
- **`aegis serve` refuses to start** if `pipeline.tool_call` or
  `pipeline.tool_result` is set — those stages were never enforced. Govern
  MCP tools in Python with `McpExecuteNode`.
- **`pip install aegis-gateway` no longer installs LLM Guard** (or PyTorch).
  The pack is still included; install its model library with
  `pip install "aegis-gateway-pack-llm-guard[llm-guard]"`. LLM Guard's pinned
  dependencies carry known advisories, so this keeps them out of default installs.
- **Budgets** must be listed in both stages (`ingress: [budget]`,
  `egress: [budget]`) — the egress half is what records spend.
- **Chroma collections** created by `ChromaVectorStore` / `aegis rag` are now
  named `aegis-<namespace>`; re-index documents stored by earlier versions.
- **`secret://` references must include `#key`** (e.g.
  `secret://env/OPENAI_API_KEY#value`); the key is ignored by the `env` backend.
- Removed: the `aegis dev` command (use `aegis serve --no-auth`), the pluggy
  hooks in `aegis_core.hooks` (never called — use exporters), the TypeScript
  SDK (generate a client from `openapi.json` instead), the `rag.chunking`,
  `rag.chroma_store` and `rag.pgvector_store` helpers (use `TextChunker`,
  `ChromaVectorStore`, `PgVectorStore`), and the Prometheus/Grafana compose
  profile (`/metrics` is unchanged).

### Security

- Dependencies upgraded across the board. Known advisories in a default
  install went from 115 (14 packages) to 7 accepted ones that don't reach
  Aegis (Chroma server endpoints; cryptography X.509/PKCS#7 APIs, pending a
  Presidio release). CI now fails on any new advisory (`scripts/audit-deps.sh`),
  and Dependabot proposes weekly updates.
- Docs toolchain: Vite upgraded to 7.x under VitePress (dev-server advisories).
- GitHub Actions moved to Node 24 releases; the dev image uses Node 24 LTS.
- Streamed `/v1/chat/completions` requests on true-streaming routes skipped
  every ingress node (PII masking, residency, budgets) and were never
  recorded. Ingress now always runs first and streamed runs are recorded.
- Tool-call and tool-result stages in `aegis.yaml` were silently ignored; the
  server now fails closed (see above).

### Added

- **`aegis serve` builds everything from `aegis.yaml`** — providers, packs
  (via `aegis.packs` factories), per-route pipelines, API-key auth — and
  `GET /v1/health` reports the config digest.
- **`aegis explain`** — the verdict-by-verdict trail of any run.
- **Evidence ledger** — hash-chained `model_inventory` and `run_evidence`
  records in SQLite; `aegis audit export | verify | inventory`,
  `GET /v1/audit/ledger`, and a published
  [record schema](https://e-choness.github.io/aegis/evidence-record.schema.json).
- **Compliance report** — `GET /v1/audit/report` and `aegis report summary`
  (route inventory, run counts, chain length); route `owner`, `risk_rating`
  and `review_interval_days` in `aegis.yaml`.
- **Named approvers** — `approvers` on runs, `aegis runs create --approver`,
  and residency `require_approval: true` to pause instead of block.
- **Exporters** — forward every ledger record to other systems with
  `exporters:` in `aegis.yaml`; built-in `jsonl` and `webhook`, plus any
  `aegis.exporters` plugin. Delivery is ordered, non-blocking, and failures
  are counted in `aegis_exporter_failures_total`.
- **Plugin author path** — `aegis plugin new` scaffolds a guardrail, node,
  provider or exporter package with passing contract tests; `aegis plugin test`
  runs an independent conformance check. Public pack API in `aegis_core.packs`.
- **Provider plugins** — any non-built-in provider `type:` loads from the
  `aegis.providers` entry-point group.
- **PII detection controls** — `entities`, `threshold` and `allow_list`
  options, a Luhn-checked Canadian SIN recognizer, and consistent placeholders
  (the same value keeps the same placeholder for the whole run).
- **Durable runs** — `aegis serve --runs-db` (SQLite) keeps runs, event logs
  and paused approvals across restarts.
- **`aegis serve --demo`** — per-visitor rate limiting for public demos.
- `GET /v1/models` for OpenAI-compatible UIs such as Open WebUI.
- `aegis policy lint` checks: unenforceable stages (`AEG-POL-004`),
  endpoint-region vs. declared residency (`AEG-POL-005`), and uninstalled
  exporter types (`AEG-POL-006`).
- Release automation: tag-triggered PyPI publishing with Trusted Publishing,
  GitHub Releases from this changelog, and the Hugging Face demo deployed
  from `deploy/huggingface/`. Every package has a PyPI description.
- A new documentation site, with this changelog on it.

### Fixed

- `anthropic` and `openai_compatible` providers could not be built from
  `aegis.yaml`; self-hosted model names behind `openai_compatible` now work.
- Budgets never accumulated spend.
- Chat runs were always recorded as `completed` with no events; blocked and
  paused chats now return `finish_reason: content_filter`.
- A paused run lost the verdict that paused it, so `aegis explain` and the
  approvals UI couldn't show why it was waiting.
- `ChromaVectorStore.query()` ignored the query vector; short namespaces
  crashed Chroma.
- Demo rate limiting died after 100 lifetime requests and shared one quota
  across all visitors behind a proxy.
- The showcase page only offered the `default` route and never listed paused
  runs for approval.

## [2.0.0a0] - 2026-06-21

First public alpha on PyPI (tagged `v0.1.0` in git).

- **Kernel** — typed `aegis.yaml` configuration, `secret://` resolution,
  entry-point plugin discovery, and a LangGraph pipeline of ingress → execute
  → egress nodes compiled per route.
- **Four-verdict guardrails** — `allow`, `sanitize`, `block`,
  `require_approval`, with checkpointed pause/resume and `aegis runs
  approve | deny`.
- **APIs** — OpenAI-compatible `/v1/chat/completions` (with SSE streaming and
  capability negotiation) and the native `/v1/runs` API; API-key auth with
  `aegis keys`.
- **Providers** — LiteLLM-backed providers, any OpenAI-compatible endpoint,
  and a `fake` provider for zero-credential development.
- **Policy packs** — PII masking (Presidio), LLM Guard, classification,
  residency and budgets.
- **Tool and retrieval governance** — MCP tool-call and tool-result guards,
  and a guarded RAG retrieval node with Chroma and pgvector stores.
- **Observability** — OpenTelemetry run spans and Prometheus metrics.
- **Tooling** — the `aegis` CLI (`init`, `serve`, `chat`, `doctor`,
  `policy lint | test`, `plugin`, `provider`, `rag`), Python and TypeScript
  SDKs, an OpenAPI spec, contract test kits, and a showcase page with a
  Hugging Face demo.
