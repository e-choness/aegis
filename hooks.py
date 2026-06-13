"""mkdocs build hook — copies openapi.json into docs/assets/ before build."""

import shutil
from pathlib import Path


def on_pre_build(config, **kwargs):  # noqa: ARG001
    src = Path("openapi.json")
    dst = Path("docs/assets/openapi.json")
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.exists():
        shutil.copy(src, dst)
