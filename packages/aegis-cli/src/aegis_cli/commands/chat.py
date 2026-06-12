"""CLI command: `aegis chat`."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Annotated

import typer
from rich.console import Console

from aegis_core.pipeline import PipelineAssembler, RunState
from aegis_core.providers.models import Message
from aegis_core.testing import FakeProvider

_console = Console()
_err_console = Console(stderr=True, style="bold red")


def chat(
    message: Annotated[str, typer.Argument(help="The message to send.")],
    route: Annotated[
        str,
        typer.Option("--route", "-r", help="Route name to use."),
    ] = "default",
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit JSON with the full event log."),
    ] = False,
) -> None:
    """Send *message* through the pipeline and print the response."""
    provider = FakeProvider(
        name="fake",
        complete_response=f"[fake] echo: {message}",
    )

    assembler = PipelineAssembler()
    pipeline = assembler.compile(provider=provider, route=route)

    initial_state = RunState(
        run_id=str(uuid.uuid4()),
        route=route,
        messages=[Message(role="user", content=message)],
    )

    result = asyncio.run(pipeline.run(initial_state))

    if json_output:
        output = {
            "run_id": result.run_id,
            "route": result.route,
            "status": result.status,
            "response": result.response,
            "events": [e.to_dict() for e in result.events],
            "usage": {
                "prompt_tokens": result.usage.prompt_tokens,
                "completion_tokens": result.usage.completion_tokens,
                "total_tokens": result.usage.total_tokens,
                "cost": result.usage.cost,
            },
        }
        _console.print(json.dumps(output, indent=2), markup=False)
    else:
        _console.print(result.response or "", markup=False)
