# Aegis public demo — Hugging Face Space (Docker SDK).
#
# Installs a released version of Aegis from PyPI; no source code is copied.
# The release workflow replaces __AEGIS_VERSION__ when it uploads this folder
# to the Space. To try it locally:
#
#   docker build --build-arg AEGIS_VERSION=2.0.0a4 -t aegis-space deploy/huggingface
#   docker run --rm -p 7860:7860 aegis-space      # http://localhost:7860

FROM python:3.12-slim

ARG AEGIS_VERSION=__AEGIS_VERSION__
ARG CONTENT_MODEL=fastino/gliner2-base-v1

# CPU-only PyTorch first: the default wheel bundles CUDA (~3 GB) the Space can't use.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Only what the demo uses, rather than the umbrella package.
RUN pip install --no-cache-dir \
        "aegis-gateway-cli==${AEGIS_VERSION}" \
        "aegis-gateway-pack-pii[pii]==${AEGIS_VERSION}" \
        "aegis-gateway-pack-residency==${AEGIS_VERSION}" \
        "aegis-gateway-pack-classification==${AEGIS_VERSION}" \
        "aegis-gateway-pack-budgets==${AEGIS_VERSION}" \
        "aegis-gateway-pack-content[model]==${AEGIS_VERSION}" \
    && python -m spacy download en_core_web_sm

# Spaces run containers as uid 1000.
RUN useradd --create-home --uid 1000 user
USER user
WORKDIR /home/user/app

# Bake the content model (~830 MB) into the image: no download at startup, and
# warm-up only has to load it (~35 s on the Space's 2 CPUs; /v1/health reports it).
ENV HF_HOME=/home/user/.cache/huggingface \
    HF_HUB_OFFLINE=1 \
    OMP_NUM_THREADS=2
RUN HF_HUB_OFFLINE=0 python -c "from gliner2 import GLiNER2; GLiNER2.from_pretrained('${CONTENT_MODEL}')"

COPY --chown=user aegis.yaml .

EXPOSE 7860
CMD ["aegis", "serve", "--config", "aegis.yaml", "--no-auth", "--demo", \
     "--host", "0.0.0.0", "--port", "7860", \
     "--ledger-db", "/tmp/aegis_ledger.db", "--runs-db", "/tmp/aegis_runs.db", \
     "--checkpoint-db", "/tmp/aegis_checkpoints.db"]
