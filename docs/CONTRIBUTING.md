# Contributing

Thanks for helping. Start with the [codebase tour](/develop/codebase) — it
explains where things live and where a change should go. The
[introduction's status table](/guide/#where-things-stand) lists capabilities
that exist as Python APIs but aren't wired into `aegis serve` yet; those make
good first contributions.

## Development environment

Everything — installs, tests, lint, docs — runs **inside Docker**. You need
Docker (with Compose v2) and Git; nothing else on the host.

```bash
git clone https://github.com/e-choness/aegis && cd aegis
docker compose build dev
docker compose run --rm dev uv sync --all-packages
```

Handy alias:

```bash
alias dc="docker compose run --rm dev"
dc uv run pytest -q
dc uv run aegis serve --config examples/dev.yaml --no-auth
```

Don't `pip install` / `uv sync` / `npm install` on the host — the lockfiles
and native wheels are built for the container.

## Before you open a PR

```bash
dc uv run ruff check .
dc uv run pyright
dc uv run lint-imports                  # packs may only use public aegis_core APIs
dc uv run pytest -q                     # all packages + Python SDK
dc uv run pytest tests/docs -q          # README + every snippet in docs/
dc bash -c "npm ci && npm run docs:build"
```

- New behaviour has tests; tests make no real network calls (use
  `FakeProvider` and the contract kits).
- Credentials exist only as `SecretStr` or `secret://` URIs.
- New errors use `AEG-<AREA>-<NNN>` with what/why/fix and are added to the
  [error reference](/reference/errors).
- User-visible changes update the docs in the same PR.
- **Don't weaken a test to make it pass.** If a gate can't go green, open an
  issue describing why.

## Working on the docs

The site is [VitePress](https://vitepress.dev/) in `docs/`. Preview it with
hot reload:

```bash
docker compose --profile docs up docs      # http://localhost:5173/aegis/
```

- Sidebar and nav live in `docs/.vitepress/config.mts`.
- Diagrams are ` ```mermaid ` blocks; `<Verdict kind="block" />` renders a
  verdict chip.
- Python blocks are linted and `aegis.yaml` blocks are validated against
  `AegisConfig` by `tests/docs` — keep them runnable and current.
- Document what the code does today. If something is planned, say so
  explicitly rather than describing it as present.

The README's animated terminal is generated from
`scripts/gen-terminal-demo.cjs`:

```bash
dc node scripts/gen-terminal-demo.cjs images/terminal-demo.svg
```

## Commits

[Conventional Commits](https://www.conventionalcommits.org/), scoped by
package or area:

```text
feat(pack-pii): support detect mode per entity type
fix(server): return 409 when resuming a completed run
docs(guide): document background runs
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `chore`.
`CHANGELOG.md` is generated from these by git-cliff.

## Plugins live outside this repo

You don't need a PR here to add a guardrail, node or provider — publish an
`aegis-<kind>-<name>` package. See [Write a plugin](/develop/plugins). PRs
that make a new kind of plugin *possible* (a contract, a wiring point) are
very welcome.

## Code of conduct

This project follows the [Contributor Covenant 2.1](./CODE_OF_CONDUCT.md).
