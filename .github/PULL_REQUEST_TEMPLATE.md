## Summary

<!-- What does this PR do? Link the relevant issue: Fixes #NNN -->

## Changes

<!-- Bullet list of what changed and why -->

## Gate checklist

All gates must be green before merge. Run inside Docker:

```bash
docker compose run --rm dev uv run pytest -q
docker compose run --rm dev uv run ruff check .
docker compose run --rm dev uv run pyright
docker compose run --rm dev uv run mkdocs build --strict
```

- [ ] `pytest -q` passes (all tests green, no warnings promoted to errors)
- [ ] `ruff check` passes (no lint errors)
- [ ] `pyright` passes (no type errors)
- [ ] `mkdocs build --strict` passes (docs build without warnings)
- [ ] No real API keys or secrets in code, tests, or fixtures
- [ ] Conventional commit message: `type(scope): description`
- [ ] New guardrail/feature has tests; no placeholder `TODO` implementations

## Breaking changes

<!-- List any breaking changes to the public API, config schema, or CLI.
     If none, write "None." -->

## Documentation

<!-- Which docs pages were updated? If none needed, write "N/A." -->
