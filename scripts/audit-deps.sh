#!/usr/bin/env bash
# scripts/audit-deps.sh — fail on any known vulnerability in locked dependencies.
#
#   docker compose run --rm dev bash scripts/audit-deps.sh
#
# Audits the exact versions in uv.lock (the default workspace install, which is
# what CI tests and `pip install aegis-gateway` resolves to) with pip-audit, and
# the docs toolchain with `npm audit`.
#
# Accepted advisories are listed below with the reason each doesn't reach Aegis.
# Remove an entry as soon as a fixed release is usable; review this list on
# every dependency upgrade.

set -euo pipefail

ACCEPTED=(
  # chromadb (no fixed release yet) — all four are in Chroma's *server*: its
  # HTTP API (trust_remote_code model loading) and multi-tenant RBAC. Aegis only
  # embeds Chroma in-process and never runs or exposes a Chroma server.
  PYSEC-2026-311    # CVE-2026-45829
  PYSEC-2026-3813   # CVE-2026-45830
  PYSEC-2026-3814   # CVE-2026-45833
  PYSEC-2026-3815   # CVE-2026-45831
  # cryptography < 49 (Presidio caps it at <49) — X.509 chain validation and
  # PKCS#7 decryption. Aegis never calls those APIs (TLS goes through Python's
  # ssl module; Presidio uses cryptography's AES helpers only).
  PYSEC-2026-3552   # CVE-2026-69247
  PYSEC-2026-3553   # CVE-2026-69249
  PYSEC-2026-3554   # CVE-2026-69248
)

ignore_args=()
for id in "${ACCEPTED[@]}"; do ignore_args+=(--ignore-vuln "$id"); done

requirements="$(mktemp)"
trap 'rm -f "$requirements"' EXIT

echo "== Python (uv.lock)"
uv export --all-packages --no-hashes --no-emit-workspace --format requirements-txt -q > "$requirements"
uvx pip-audit --requirement "$requirements" --no-deps --disable-pip \
  --progress-spinner off "${ignore_args[@]}"

echo "== npm (docs toolchain)"
npm audit --audit-level=low
