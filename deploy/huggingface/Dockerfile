# Aegis public demo — Hugging Face Space (Docker SDK).
#
# Installs a released version of Aegis from PyPI; no source code is copied.
# The release workflow replaces __AEGIS_VERSION__ when it uploads this folder
# to the Space. To try it locally:
#
#   docker build --build-arg AEGIS_VERSION=2.0.0a0 -t aegis-space deploy/huggingface
#   docker run --rm -p 7860:7860 aegis-space      # http://localhost:7860

FROM python:3.12-slim

ARG AEGIS_VERSION=__AEGIS_VERSION__

# Only what the demo uses — the umbrella package would also pull in LLM Guard
# (and PyTorch), which the demo config doesn't enable.
RUN pip install --no-cache-dir \
        "aegis-gateway-cli==${AEGIS_VERSION}" \
        "aegis-gateway-pack-pii[pii]==${AEGIS_VERSION}" \
        "aegis-gateway-pack-residency==${AEGIS_VERSION}" \
        "aegis-gateway-pack-classification==${AEGIS_VERSION}" \
        "aegis-gateway-pack-budgets==${AEGIS_VERSION}" \
    && python -m spacy download en_core_web_sm

# Spaces run containers as uid 1000.
RUN useradd --create-home --uid 1000 user
USER user
WORKDIR /home/user/app
COPY --chown=user aegis.yaml .

EXPOSE 7860
CMD ["aegis", "serve", "--config", "aegis.yaml", "--no-auth", "--demo", \
     "--host", "0.0.0.0", "--port", "7860", \
     "--ledger-db", "/tmp/aegis_ledger.db", "--runs-db", "/tmp/aegis_runs.db", \
     "--checkpoint-db", "/tmp/aegis_checkpoints.db"]
