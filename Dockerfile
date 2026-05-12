FROM python:3.12-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./

# ---- deps layer ----
FROM base AS deps
RUN pip install --no-cache-dir -e ".[dev]" && \
    python -m spacy download en_core_web_sm

# ---- source layer ----
FROM deps AS app
COPY config/ ./config/
COPY src/ ./src/
COPY tests/ ./tests/
COPY evals/ ./evals/

# ---- test target ----
FROM app AS test
ENV PYTHONPATH=/app
CMD ["pytest", "-v", "--tb=short"]

# ---- runtime target ----
FROM app AS runtime
ENV PYTHONPATH=/app
EXPOSE 8000
CMD ["uvicorn", "src.aegis.main:app", "--host", "0.0.0.0", "--port", "8000"]
