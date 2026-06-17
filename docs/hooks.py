"""mkdocs build hook — copies openapi.json and protects from bytecode."""

import shutil
from pathlib import Path


def on_pre_build(config, **kwargs):
    src = Path("openapi.json")
    dst = Path("docs/assets/openapi.json")
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.exists():
        shutil.copy(src, dst)
    src_jekyll = Path("docs/.nojekyll")
    dst_jekyll = Path("site/.nojekyll")
    dst_jekyll.parent.mkdir(parents=True, exist_ok=True)
    if src_jekyll.exists():
        shutil.copy(src_jekyll, dst_jekyll)


def on_post_build(config, **kwargs):
    for p in Path("site").glob("**/__pycache__"):
        shutil.rmtree(p, ignore_errors=True)
