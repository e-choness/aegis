# Changelog

Notable changes to Aegis, newest first. Versions follow
[PEP 440](https://peps.python.org/pep-0440/) and every package in a release
shares one version. The format follows [Keep a Changelog](https://keepachangelog.com/).

Changes land under **Unreleased** as they merge; on release that section
becomes the version's entry and its GitHub Release notes.

## [Unreleased]

### Added

- `scripts/cli-tour.sh` (config `examples/cli-tour.yaml`): the session the
  README's terminal replay shows — plugin list, a blocked credential, a clean
  run, an approval denied by a reviewer, `explain`, ledger verify. CI runs it.
- A new docs home page.
- Demo: a "Reset my budget" button on the Budgets tab (and a per-visitor
  `POST /showcase/api/budget/reset`, `--demo` only), so visitors can watch
  the cap trip again. Nodes and guards may define `reset_usage(principal)`;
  `PipelineExecutor.reset_usage(route, principal)` calls it.
- `backend: stub` for the content pack: no model, no entities, the first value
  for every label — for tests, CI and offline runs. CI's demo smoke test uses
  it via `AEGIS__GUARDRAILS__<NAME>__BACKEND=stub`.
- PII redaction in replies: `pii.redact` checks the model's reply before the
  user's values are restored, so anything it finds came from the model; each
  hit becomes an irreversible `[ENTITY]` label, recorded as `sanitize`. On by
  default for every default entity except `PERSON` (`redact_output`,
  `redact_entities`). The PII pack's egress is now `[pii.redact, pii.unmask]`.
- `unmask_response: false` on a route keeps placeholders in the reply, for
  output that goes to third parties.
- A *Design notes* page in the docs (Develop), starting with restoring values
  at the server edge — deferred, with what would make it worth revisiting.

### Changed

- `sanitize` now shows up in real runs. Masking by the PII and content packs
  records a `sanitize` verdict naming what was masked (types and counts,
  never values), and a RAG passage withheld by a guard is recorded as
  `sanitize` instead of `block` — the run goes on without it, so `aegis
  explain` no longer shows BLOCK on a completed run. The showcase says what
  was sanitized on a run that went through.
- A tool result that a guard rejects (e.g. it carries "ignore all previous
  instructions") is now **withheld** instead of blocking the run: the model is
  told the result was withheld and carries on, recorded as `sanitize`. Set
  `on_unsafe_tool_result: block` on a route (or `on_unsafe_result="block"` on
  `McpExecuteNode`) for the old behaviour.

### Fixed

- A dotted name in a stage list, e.g. `egress: [pii.unmask]`, passed
  validation and `aegis policy lint` but built nothing — so the reply kept its
  placeholders. It now places that one node of the pack, and a name matching
  no node fails at startup.
- A guard returning `Verdict.sanitize` replaced every message in the
  conversation — system prompt and earlier turns included — with the
  replacement; it now replaces the latest user message, the one guards scan.
- On a true-streaming route, a chunk a guard sanitized was sent unchanged;
  the replacement is now sent, and the verdict recorded.
- Docs diagrams could show "Syntax error in text" instead of rendering: the
  mermaid plugin re-rendered every diagram on any change to the page's root
  element, and overlapping renders clobbered each other. Diagrams now render
  one at a time and only when the colour theme changes.
- `aegis serve` printed install hints without their extras
  (`pip install "aegis-gateway-pack-content"` instead of `…[model]`): error
  text is no longer read as console markup.
- `aegis explain` no longer prints `reason=None` for allow verdicts or repeats
  the guard name next to the node that already shows it.

## [2.0.0a5] - 2026-09-27

### Fixed

- 2.0.0a4's `aegis-gateway-server` was published without three new files
  (`recording.py`, `showcase_tabs.py`, `static/showcase.html`) and fails at
  import; install 2.0.0a5 instead. The release now installs the built wheels
  in a clean environment, imports every module and serves a request before
  anything is published.

## [2.0.0a4] - 2026-09-27

### Added

- `aegis-gateway-pack-content` (`pack: aegis.content`): a local model labels
  requests and masks entities no pattern can describe (e.g. internal
  hostnames). GLiNER2 by default, swappable through the
  `aegis.content_models` entry point; install the model with
  `pip install "aegis-gateway[content]"`. Its measured accuracy is on the
  [pack page](/packs/content).
- `aegis_core.masking`: one placeholder scheme and `mask_map` shared by every
  masking pack; a single unmask on egress restores everything.
- The showcase has one tab per scenario — privacy, content policy, prompt
  attacks, residency and approval, agent tools, budgets, audit — built from
  the config: a route's `showcase:` block puts it on a tab with click-to-try
  presets. Every result shows each step's timing, labels, masked values, tool
  calls and budget, plus the YAML behind the route and a `curl` for it; the
  Audit tab explains runs, verifies the chain and downloads the evidence.
- Budget events report `spent` and `cap`.
- A *Model evals* CI workflow scores the content pack's model against
  `evals/baseline.json`.

### Changed

- Labels written by different packs are merged instead of the last one
  replacing the rest.

### Fixed

- Showcase runs were missing from the audit trail: they now store their
  events and append evidence to the ledger like `/v1/runs`, so they can be
  explained and verified.

### Removed

- `aegis-gateway-pack-llm-guard`. LLM Guard pinned vulnerable dependencies,
  conflicted with the PII extra and reloaded its model on every request;
  model-based detection moves to the content pack. Its last release stays on
  PyPI.

## [2.0.0a3] - 2026-09-26

### Changed

- PII masking no longer masks `LOCATION` by default: a place name rarely
  identifies anyone, and it caused most false alarms in the new guard evals.
  Add it back with `entities: [..., LOCATION]`.
- PII masking detects what does pinpoint a person: street addresses
  (`STREET_ADDRESS`, including unit numbers, PO boxes and French-order
  streets) and postal codes (`POSTAL_CODE`: Canadian, UK, US ZIP+4 or
  state + ZIP), both on by default.
- Classification labels are checked most severe first (`secret`, `financial`,
  `pii`, …), so a message with an email address and a password is `secret`.
- Classification recognises many more credential shapes — private keys,
  AWS/Google/GitHub/Slack/Stripe keys, JWTs, bearer tokens, connection strings
  with passwords, `DB_PASSWORD=…` — and no longer labels mentions such as
  `password: required` or `"token": null` as secrets. Secret recall on the
  guard evals rose from 22% to 100% with no false alarms.

### Added

- Tools in `aegis.yaml`: a route's `tools:` declares what the model may call,
  each with a canned `result`, `require_approval` or `deny`; `tool_guards:`
  adds the built-in `exfiltration` and `injection` guards. The `fake`
  provider scripts tool calls with `tool_calls:`.
- Approving a paused tool call now runs the call and continues the run —
  before, approval skipped the call and the run ended without a reply.
- `aegis.policy` (in `aegis-gateway-pack-classification`): rules that turn
  labels into verdicts — e.g. `secret` blocks, `pii` requires approval.
- Residency `apply_when: sensitive`: enforce only for requests that carry
  personal or sensitive data (PII was masked, or a sensitive label); other
  requests may use the endpoint wherever it is.
- Per-step timing: every `node_end` event records `duration_ms`, and the
  showcase shows each step's time and the pipeline total.
- Warm-up at startup: nodes and guards may define `warmup()`; the server
  calls it in the background and `/v1/health` reports `warmup: warming |
  ready | failed: …`. The PII pack loads spaCy and Presidio this way, so the
  first request no longer waits ~9 s.
- `GET /v1/audit/verify` checks the evidence ledger's hash chain in place.
- The `fake` provider's `cost_per_request` reports a cost per completion, so
  budgets can be demonstrated; in `--demo` mode each showcase visitor gets
  their own principal (a hash of their address), so budgets and runs are
  per visitor.
- Guard evals: `evals/probes.jsonl` (labelled prompts) and
  `scripts/eval_guards.py`, which scores each detector's precision, recall and
  latency; CI fails when a score drops below `evals/baseline.json`.

### Fixed

- PII masking no longer reports timestamps such as `2026-09-26 // 11` as phone
  numbers.
- Showcase: "Refresh runs" shows the newest runs and visibly refreshes.

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
