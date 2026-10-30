FROM python:3.12-slim-bookworm

# Install UV binary from official Astral image
COPY --from=ghcr.io/astral-sh/uv:0.6.5 /uv /uvx /bin/

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV PYTHONUNBUFFERED=1

# Copy dependency manifests first for optimal Docker layer caching
COPY pyproject.toml uv.lock* ./

# Install project dependencies
RUN uv sync --frozen --no-install-project --no-dev || uv sync --no-install-project --no-dev

# Copy application source code and migrations config
COPY alembic.ini ./
COPY app ./app

# Create fixtures placeholder directory (can be mounted via docker volume)
RUN mkdir -p /app/fixtures/XLIFF

# Final project sync
RUN uv sync --no-dev

EXPOSE 8000

# API: migrate, then serve. The worker service overrides this with `python -m app.worker`.
CMD ["sh", "-c", "uv run --no-sync alembic upgrade head && uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port 8000"]
