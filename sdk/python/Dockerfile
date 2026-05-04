FROM python:3.12-slim AS base

WORKDIR /app

COPY pyproject.toml ./

# ---- deps layer ----
FROM base AS deps
RUN pip install --no-cache-dir -e ".[dev]"

# ---- source layer ----
FROM deps AS app
COPY src/ ./src/
COPY tests/ ./tests/

# ---- test target ----
FROM app AS test
ENV PYTHONPATH=/app/src
CMD ["pytest", "-v", "--tb=short"]
