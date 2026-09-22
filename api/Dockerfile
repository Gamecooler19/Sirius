# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS base

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

FROM base AS builder
COPY api/pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-project --no-dev

COPY api/. .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev

FROM base AS runtime
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 38210

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "38210"]
