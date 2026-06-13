# Contributing to Aegis

Thank you for your interest in contributing to Aegis. This guide covers the
development environment, gate policy, commit conventions, and plugin authoring.

## Development environment

Aegis uses Docker exclusively for all build steps. You must have Docker running
before starting any work.

### Prerequisites

- Docker Desktop (or Docker Engine + Compose v2)
- Git

### Setup

```bash
git clone https://github.com/e-choness/aegis
cd aegis
docker compose build dev
```

All commands run inside Docker via the `dev` service:

```bash
# Alias for convenience
alias DC="docker compose run --rm dev"

DC uv run pytest -q          # run tests
DC uv run ruff check .       # lint
DC uv run pyright            # type-check
DC uv run aegis dev          # start dev server
```

**Never** run `pip`, `uv`, `pytest`, or `npm` directly on your host. Every
install, test, lint, and type-check must run inside Docker.

## Gate policy

Every pull request must pass the full test suite:

```bash
DC uv run pytest -q
DC uv run ruff check .
DC uv run pyright
DC uv run lint-imports
DC uv run mkdocs build --strict
DC uv run pytest tests/docs -q
```

**Do not weaken a test to make it pass.** If a gate cannot be made green,
open an issue describing the failure before submitting the PR.

## Conventional commits

Aegis uses [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short description>

feat(guardrails): add incremental scan_chunk support
fix(server): handle missing run_id in resume endpoint
docs(tutorials): add five-minute gateway tutorial
test(pii): add edge case for overlapping entities
chore(ci): update Docker base image to python:3.12
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `perf`.
Scope is the package or area changed.

## Pull request checklist

Before opening a PR, verify:

- [ ] `DC uv run pytest -q` — all tests pass
- [ ] `DC uv run ruff check .` — zero lint errors
- [ ] `DC uv run pyright` — zero type errors
- [ ] `DC uv run lint-imports` — import contracts satisfied
- [ ] `DC uv run mkdocs build --strict` — docs build clean
- [ ] New behaviour has tests; tests do not make real network calls
- [ ] Secrets appear only as `SecretStr` or `secret://` URIs — never plain strings
- [ ] Error messages use `AEG-<AREA>-<NNN>` codes

## Plugin authoring

Third-party plugins follow the `aegis-<kind>-<name>` naming convention:

- `aegis-guardrail-<name>` — custom guardrails
- `aegis-provider-<name>` — custom model providers
- `aegis-secrets-<name>` — custom secret backends

Scaffold a plugin:

```bash
DC aegis plugin scaffold guardrail my-guard
```

The scaffold generates a publishable package with contract tests. Publish to
PyPI with the `aegis.guardrails` (or appropriate) entry point declared in
`pyproject.toml`.

See the [plugin authoring tutorial](tutorials/first-guardrail.md) for a
full walkthrough.

## Code of conduct

This project follows the [Contributor Covenant 2.1](CODE_OF_CONDUCT.md).
