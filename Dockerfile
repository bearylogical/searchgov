# ── Stage 1: Build SvelteKit frontend ───────────────────────────────────────
FROM node:22-alpine AS frontend-builder

WORKDIR /build/frontend

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


# ── Stage 2: Python backend ──────────────────────────────────────────────────
FROM python:3.11-slim AS backend

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Disable uv cache — the non-root runtime user has no writable home dir
ENV UV_NO_CACHE=1

WORKDIR /app

# Copy dependency manifests first for better layer caching
COPY pyproject.toml uv.lock ./

# Install third-party dependencies only (skip building the local package
# so this layer is cached independently of source changes)
RUN uv sync --frozen --no-dev --no-install-project

# Copy application source
COPY src/ src/
COPY api_main.py ./

# Copy compiled frontend assets (served statically by FastAPI)
COPY --from=frontend-builder /build/frontend/build ./frontend/build

# Run as non-root
RUN addgroup --system app && adduser --system --ingroup app app
USER app

EXPOSE 8081

CMD ["uv", "run", "uvicorn", "api_main:app", "--host", "0.0.0.0", "--port", "8081"]
