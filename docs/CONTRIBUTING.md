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
dc bash scripts/audit-deps.sh           # known vulnerabilities in uv.lock and the docs toolchain
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

## Dependencies and security

- `uv.lock` pins every Python dependency; `uv lock --upgrade` refreshes it.
  Dependabot opens grouped weekly PRs for Python, npm, GitHub Actions and base
  images.
- `scripts/audit-deps.sh` runs in CI and fails on any known advisory. The few
  accepted ones are listed in the script with the reason they don't reach
  Aegis — remove an entry as soon as a fixed release is usable.
- LLM Guard's extra is resolved separately in `uv.lock` (`[tool.uv] conflicts`
  in the root `pyproject.toml`) so its exact pins can't hold back the rest of
  the workspace; its tests stub the library.
- `package.json` overrides Vite to a patched 7.x: VitePress 1.6 still pins
  Vite 5, whose dev server has unfixed advisories. Drop the override once
  VitePress 2 is stable.

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

## Releasing

**The git tag is the version.** No package declares one: `hatch-vcs` reads it
from git at build time, so tag `v2.0.0a3` builds as `2.0.0a3`, and every commit
after it as `2.0.0a4.devN` (that's what `aegis --version` shows in a dev
checkout). Internal dependencies are unpinned in the repo and pinned exactly
(`==2.0.0a3`) by the release build. To release:

```bash
dc uv run python scripts/release.py changelog 2.0.0a3   # Unreleased → [2.0.0a3] - <today>
git commit -am "docs: changelog for 2.0.0a3"
git tag v2.0.0a3
git push origin main v2.0.0a3
```

The changelog step is optional — without it the release notes use the
*Unreleased* section — but it keeps the changelog page tidy. Tags follow
PEP 440 with a `v` prefix: `v2.0.0`, `v2.1.0a1`, `v2.1.0rc1`.

The tag triggers `.github/workflows/release.yml`, which:

1. pins internal dependencies to the tag's version and builds the ten
   published packages (never the test fixture plugin);
2. fails unless every built file is exactly that version
   (`release.py verify`) and `twine check --strict` passes, so a README PyPI
   can't render fails the build;
3. publishes the components, then `aegis-gateway`, to PyPI with Trusted
   Publishing — no API token is stored in GitHub, and files that already exist
   are skipped, so re-running is safe;
4. creates a GitHub Release whose notes are that version's section of
   [`docs/changelog.md`](/changelog);
5. waits until the version is installable, then uploads `deploy/huggingface/`
   to the demo Space pinned to that version.

**One-time setup.** On PyPI, add a *trusted publisher* (project → Settings →
Publishing) to **every one** of the ten projects — `aegis-gateway`,
`aegis-gateway-core`, `-server`, `-cli`, `-sdk`, `-pack-pii`,
`-pack-llm-guard`, `-pack-classification`, `-pack-residency`,
`-pack-budgets` — with owner `e-choness`, repository `aegis`, workflow
`release.yml`, environment `pypi`. A project without one rejects the upload
(403). Components are published first and `aegis-gateway` last, so a failure
never leaves an umbrella release pointing at components that don't exist. In the GitHub repo, create an environment named `pypi`,
and for the demo Space set the variable `HF_SPACE_ID` (e.g. `e-choness/aegis-demo`)
and the secret `HF_TOKEN` (a Hugging Face token with write access). Without
`HF_SPACE_ID` the Space job is skipped.

PyPI only limits how quickly *new projects* can be created; new versions of
existing projects upload in one step. If you ever add a new package, create
its project first (a manual upload or a pending trusted publisher) before
tagging.

## Commits

[Conventional Commits](https://www.conventionalcommits.org/), scoped by
package or area:

```text
feat(pack-pii): support detect mode per entity type
fix(server): return 409 when resuming a completed run
docs(guide): document background runs
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `chore`.
Add user-visible changes to the *Unreleased* section of [](/changelog) in the same PR
(`uv run git-cliff --unreleased` drafts entries from these commits).

## Plugins live outside this repo

You don't need a PR here to add a guardrail, node or provider — publish an
`aegis-<kind>-<name>` package. See [Write a plugin](/develop/plugins). PRs
that make a new kind of plugin *possible* (a contract, a wiring point) are
very welcome.

## License

Aegis is licensed under the [GNU AGPL-3.0-or-later](https://github.com/e-choness/aegis/blob/main/LICENSE).
By submitting a contribution you agree that it is licensed under the same
terms.

## Code of conduct

This project follows the [Contributor Covenant 2.1](./CODE_OF_CONDUCT.md).
