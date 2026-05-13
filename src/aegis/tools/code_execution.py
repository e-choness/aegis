from __future__ import annotations

import ast
import asyncio
import sys
from dataclasses import dataclass, field
from typing import Any

from ..services.team_context import TeamContext
from ..services.tool_registry import ToolDefinition

_MAX_OUTPUT_BYTES = 10_000
_BLOCKED_CALLS = {"eval", "exec", "compile", "open", "input", "__import__"}
_BLOCKED_ATTRIBUTES = {
    ("os", "system"),
    ("os", "popen"),
    ("subprocess", "run"),
    ("subprocess", "Popen"),
    ("subprocess", "call"),
    ("socket", "socket"),
}


def validate_python_code(code: str) -> list[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"syntax error: {exc.msg}"]

    errors: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            errors.append("imports are blocked in the code execution sandbox")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in _BLOCKED_CALLS:
                errors.append(f"{node.func.id} is blocked in the code execution sandbox")
            if isinstance(node.func, ast.Attribute):
                root = _attribute_root(node.func)
                if root and (root, node.func.attr) in _BLOCKED_ATTRIBUTES:
                    errors.append(f"{root}.{node.func.attr} is blocked in the code execution sandbox")
    return errors


def _attribute_root(node: ast.Attribute) -> str | None:
    value = node.value
    while isinstance(value, ast.Attribute):
        value = value.value
    if isinstance(value, ast.Name):
        return value.id
    return None


@dataclass
class CodeExecutionTool:
    definition: ToolDefinition = field(default_factory=lambda: ToolDefinition(
        name="code_execute",
        description="Execute small Python snippets in a constrained subprocess",
        input_schema={
            "type": "object",
            "required": ["language", "code"],
            "properties": {
                "language": {"type": "string", "enum": ["python"]},
                "code": {"type": "string", "minLength": 1, "maxLength": 20000},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 30},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "stdout": {"type": "string"},
                "stderr": {"type": "string"},
                "exit_code": {"type": "integer"},
            },
        },
        min_tier=3,
        data_classification="RESTRICTED",
        cost_per_call_usd=0.05,
        requires_approval=True,
        timeout_seconds=30,
        safety_validators=["sandbox", "ast_analysis"],
    ))

    def validate(self, args: dict[str, Any]) -> list[str]:
        if args.get("language") != "python":
            return ["only python execution is currently supported"]
        return validate_python_code(str(args.get("code", "")))

    async def execute(self, team_context: TeamContext, args: dict[str, Any]) -> dict[str, Any]:
        timeout = min(int(args.get("timeout_seconds", 10)), 30)
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            "-c",
            str(args["code"]),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            return {"stdout": "", "stderr": "execution timed out", "exit_code": 124}

        return {
            "stdout": stdout[:_MAX_OUTPUT_BYTES].decode("utf-8", errors="replace"),
            "stderr": stderr[:_MAX_OUTPUT_BYTES].decode("utf-8", errors="replace"),
            "exit_code": int(process.returncode or 0),
        }
