# ── Stage 1: Build SvelteKit frontend ───────────────────────────────────────
FROM node:22-alpine AS frontend-builder

WORKDIR /build/frontend

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci

COPY frontend/ ./

ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_ANON_KEY
ENV VITE_SUPABASE_URL=$VITE_SUPABASE_URL
ENV VITE_SUPABASE_ANON_KEY=$VITE_SUPABASE_ANON_KEY

RUN npm run build


# ── Stage 2: Python backend ──────────────────────────────────────────────────
FROM python:3.11-slim AS backend

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Disable uv cache — the non-root runtime user has no writable home dir
ENV UV_NO_CACHE=1

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency manifests first for better layer caching
COPY pyproject.toml uv.lock ./

# Install third-party dependencies first for better layer caching
# (skip local package — source not copied yet)
RUN uv sync --frozen --no-dev --no-install-project

# Copy application source and other required files
COPY src/ src/
COPY api_main.py README.md ./

# Copy compiled frontend assets (served statically by FastAPI)
COPY --from=frontend-builder /build/frontend/build ./frontend/build

# Install the local project into the venv now that source is present
RUN uv sync --frozen --no-dev

# Run as non-root
RUN addgroup --system app && adduser --system --ingroup app app
USER app

EXPOSE 8081

# Call uvicorn directly — avoids uv run overhead and re-sync at startup
CMD [".venv/bin/uvicorn", "api_main:app", "--host", "0.0.0.0", "--port", "8081"]
