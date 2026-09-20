"""Tests for `aegis serve` CLI command (Phase 0)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from typer.testing import CliRunner

from aegis_cli.main import app

runner = CliRunner()


# ── Helpers ───────────────────────────────────────────────────────────────────


def _write_yaml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "aegis.yaml"
    p.write_text(textwrap.dedent(content))
    return p


_FAKE_YAML = """\
providers:
  fake:
    type: fake
    complete_response: hi
routes:
  default:
    provider: fake
auth:
  type: none
"""


# ── Config-not-found ──────────────────────────────────────────────────────────


def test_serve_missing_config_exits_1(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["serve", "--config", str(tmp_path / "missing.yaml"), "--no-auth"],
    )
    assert result.exit_code == 1
    assert "not found" in result.output.lower() or "aegis init" in result.output


# ── Config-validation-error ───────────────────────────────────────────────────


def test_serve_invalid_yaml_exits_1(tmp_path: Path) -> None:
    bad = tmp_path / "aegis.yaml"
    bad.write_text("providers: [this, is, not, a, mapping]\n")
    result = runner.invoke(app, ["serve", "--config", str(bad), "--no-auth"])
    assert result.exit_code == 1


# ── dev command removed ───────────────────────────────────────────────────────


def test_dev_command_no_longer_registered() -> None:
    """The `dev` subcommand was removed in Phase 0."""
    result = runner.invoke(app, ["dev"])
    # Typer exits with 2 for unknown commands
    assert result.exit_code == 2


# ── serve --help includes --config ────────────────────────────────────────────


def test_serve_help_shows_config_option() -> None:
    result = runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == 0
    assert "--config" in result.output


# ── serve launches (mocked uvicorn) ──────────────────────────────────────────


def _patch_uvicorn_serve(monkeypatch: pytest.MonkeyPatch, launched: list[object]) -> None:
    """Replace uvicorn.Server.serve with a no-op that records the built app.

    `serve()` drives `uvicorn.Server(...).serve()` directly (not
    `uvicorn.run()`) so it can hold a checkpointer's connection open for the
    server's lifetime — see the comment in `commands/serve.py`.
    """
    import uvicorn

    async def fake_serve(self: uvicorn.Server, sockets: object = None) -> None:
        launched.append(self.config.app)

    monkeypatch.setattr(uvicorn.Server, "serve", fake_serve)


def test_serve_builds_and_calls_uvicorn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """serve() loads config, builds executor, and starts a uvicorn.Server."""
    p = _write_yaml(tmp_path, _FAKE_YAML)

    launched: list[object] = []
    _patch_uvicorn_serve(monkeypatch, launched)

    result = runner.invoke(
        app,
        ["serve", "--config", str(p), "--no-auth", "--checkpoint-db", str(tmp_path / "cp.db")],
    )
    assert result.exit_code == 0, result.output
    assert len(launched) == 1


def test_serve_prints_digest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = _write_yaml(tmp_path, _FAKE_YAML)
    _patch_uvicorn_serve(monkeypatch, [])

    result = runner.invoke(
        app,
        ["serve", "--config", str(p), "--no-auth", "--checkpoint-db", str(tmp_path / "cp.db")],
    )
    assert result.exit_code == 0, result.output
    assert "digest=" in result.output


def test_serve_resume_works_over_a_real_checkpointer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A route that pauses for approval can actually be resumed via `aegis serve`.

    Regression test: `build_executor(cfg)` used to be called with no
    checkpointer at all, so every approval-gated route would pause
    successfully but then fail to resume with "Cannot resume a run without
    a checkpointer" — `aegis serve` (unlike the test fixtures, which always
    passed a checkpointer explicitly) never actually supported HITL.

    The exchange has to happen *inside* the mocked `Server.serve()` call,
    while `serve()`'s `async with sqlite_checkpointer(...)` block is still
    open — the connection closes the moment that block exits.
    """
    import httpx
    import uvicorn

    yaml_path = _write_yaml(
        tmp_path,
        """\
        providers:
          fake:
            type: fake
            complete_response: hi
        guardrails:
          approval:
            pack: aegis.residency
            region: us-east-1
            jurisdiction: US
            allowed_regions: [ca-central-1]
            require_approval: true
        pipeline:
          ingress: [approval]
        routes:
          default:
            provider: fake
        auth:
          type: none
        """,
    )

    captured: dict[str, object] = {}

    async def fake_serve(self: uvicorn.Server, sockets: object = None) -> None:
        transport = httpx.ASGITransport(app=self.config.app)  # type: ignore[arg-type]
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            run_resp = await client.post(
                "/v1/runs", json={"messages": [{"role": "user", "content": "hi"}]}
            )
            captured["run_status"] = run_resp.json()["status"]
            run_id = run_resp.json()["run_id"]

            resume_resp = await client.post(
                f"/v1/runs/{run_id}/resume", json={"decision": "denied"}
            )
            captured["resume_status_code"] = resume_resp.status_code
            captured["resume_json"] = resume_resp.json()

    monkeypatch.setattr(uvicorn.Server, "serve", fake_serve)

    result = runner.invoke(
        app,
        [
            "serve",
            "--config",
            str(yaml_path),
            "--no-auth",
            "--checkpoint-db",
            str(tmp_path / "cp.db"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert captured["run_status"] == "paused"
    assert captured["resume_status_code"] == 200, captured["resume_json"]
    assert captured["resume_json"]["status"] == "denied"  # type: ignore[index]
