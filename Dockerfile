# Reuse the dev base image (Python 3.12, uv, spaCy baked in).
FROM python:3.12-slim

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    build-essential \
    ca-certificates \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# uv — official binary from the release image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Install spaCy + en_core_web_sm for PII pack (required by aegis-gateway-pack-pii[pii])
RUN pip install --no-cache-dir spacy click && \
    python -m spacy download en_core_web_sm

WORKDIR /app

# Install the aegis workspace (umbrella + deps).
COPY pyproject.toml uv.lock* ./
COPY packages ./packages
COPY sdk/python ./sdk/python

RUN uv sync --all-packages --python 3.12

# Copy diagnostic and fix scripts
COPY scripts/diagnose-container.sh scripts/fix-container-entrypoint.sh ./scripts/
RUN chmod +x ./scripts/*.sh

# Expose the demo port (HF Spaces defaults to 7860).
EXPOSE 7860

# Run the fix script which ensures packages are properly installed before starting the server.
# This handles the case where uv sync completes but entry points aren't properly registered.
ENTRYPOINT ["./scripts/fix-container-entrypoint.sh"]
