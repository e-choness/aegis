#!/usr/bin/env python3
"""Export the Aegis server OpenAPI schema to openapi.json.

Usage
-----
    python scripts/export_openapi.py               # write openapi.json
    python scripts/export_openapi.py --check       # exit 0 if openapi.json is up-to-date
    python scripts/export_openapi.py --output PATH # write to a custom path
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from aegis_core.pipeline.executor import PipelineExecutor
from aegis_core.testing.providers import FakeProvider
from aegis_server.app import create_app


def _build_schema() -> dict[str, object]:
    """Instantiate a minimal app and extract its OpenAPI schema."""
    ex = PipelineExecutor()
    ex.register("default", provider=FakeProvider(complete_response=""))
    app = create_app(ex, no_auth=True)
    schema: dict[str, object] = app.openapi()
    return schema


def _without_version(schema: dict[str, object]) -> dict[str, object]:
    raw_info = schema.get("info")
    info: dict[str, object] = dict(raw_info) if isinstance(raw_info, dict) else {}
    info.pop("version", None)
    return {**schema, "info": info}


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Aegis OpenAPI schema.")
    parser.add_argument(
        "--output",
        default="openapi.json",
        help="Output path (default: openapi.json in repo root).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check that openapi.json is up-to-date; exit non-zero if not.",
    )
    args = parser.parse_args()

    schema = _build_schema()
    serialized = json.dumps(schema, indent=2, sort_keys=True)

    output = Path(args.output)

    if args.check:
        if not output.exists():
            print(f"FAIL: {output} does not exist. Run: python scripts/export_openapi.py", file=sys.stderr)
            sys.exit(1)
        existing = json.loads(output.read_text(encoding="utf-8"))
        # The version comes from git (hatch-vcs) and changes with every commit;
        # only the API surface has to match.
        if _without_version(existing) != _without_version(schema):
            print(f"FAIL: {output} is out of date. Run: python scripts/export_openapi.py", file=sys.stderr)
            sys.exit(1)
        print(f"OK: {output} is up to date.")
        return

    output.write_text(serialized + "\n", encoding="utf-8")
    print(f"Wrote {output} ({len(serialized)} bytes, {len(schema.get('paths', {}))} paths)")  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
