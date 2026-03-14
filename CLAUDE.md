# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
uv sync

# Run NiceGUI web app (port 8080)
uv run main.py

# Run FastAPI server (port 8081)
uv run api_main.py

# Lint
uv run ruff check .
uv run ruff format .

# Run tests
uv run pytest
uv run pytest tests/test_clean.py::test_clean_text   # single test
```

## Architecture

This is a Singapore Government Directory Intelligence (SGDI) analytics platform. It ingests government employment records and exposes them through two parallel servers:

- **`main.py`** — NiceGUI web app on port 8080
- **`api_main.py`** — FastAPI REST API on port 8081, docs at `/docs`

Both share the same singleton `graph_facade` (`TemporalGraph`) initialized via `src/state.py`. The facade is created once on startup and injected wherever needed.

### Core layers

**`src/app/temporal_graph.py`** — The single facade that all callers (views and API routers) use. Never bypass it to call repositories or services directly from UI/API code.

**`src/state.py`** — Holds the global `graph_facade` singleton. `initialize_app_state()` / `shutdown_app_state()` are called by both app entry points via their lifespan hooks.

**Repositories** (`src/repositories/`) — Thin asyncpg wrappers: `PeopleRepository`, `OrganisationsRepository`, `EmploymentRepository`. They execute SQL and return raw `dict`s.

**Services** (`src/services/`) — Business logic built on top of repositories:
- `QueryService` — career progression, colleague discovery, temporal overlaps, network snapshots
- `OrganisationService` — org hierarchy traversal, subtree at date, timeline diffs
- `GraphService` — shortest path (temporal and static), centrality metrics
- `AnalyticsService` — turnover analysis, succession patterns
- `EmploymentService` — bulk insertion with disambiguation

**`src/database/postgres/connection.py`** — `AsyncDatabaseConnection` wraps an `asyncpg` pool. All DB access goes through its `fetch()`, `fetchrow()`, `execute()`, and `transaction()` methods.

### FastAPI layer (`src/api/`)

- `src/api/__init__.py` — `create_api()` factory, mounts all routers under `/api/v1`
- `src/api/dependencies.py` — `get_facade()` DI function, raises 503 if not ready
- `src/api/routers/` — one file per domain: `people`, `organisations`, `graph`, `analytics`, `system`
- `src/api/schemas/` — Pydantic models using v1 syntax (`class Config: orm_mode = True`) — required because `pydantic>=1.10.22` has no upper bound

### NiceGUI frontend (`src/frontend/`)

Views in `src/frontend/views/` are auto-discovered and registered as NiceGUI pages by `register_views()` in `src/frontend/utils/views.py`. Each view module exposes a `content()` function. Use `@exclude_from_scan` to opt a module out of auto-registration.

Authentication (`src/auth/__init__.py`) is Supabase-based. Set `DEV_MODE=true` in `.env` to bypass auth locally. The `AuthMiddleware` in `src/middleware/__init__.py` guards all NiceGUI routes except `/login`.

### Key environment variables

```
POSTGRES_HOST / POSTGRES_DB / POSTGRES_PORT / POSTGRES_USER / POSTGRES_PASSWORD
SUPABASE_URL / SUPABASE_KEY
LOG_LEVEL=DEBUG|INFO
DEV_MODE=true   # skips Supabase auth
```

## Code conventions

- Line length: 79 characters (enforced by `ruff.toml`)
- All DB calls are `async` — never call repository or service methods synchronously
- `loguru` is used throughout — import `from loguru import logger`, not the stdlib `logging`
- Pydantic schemas must use v1-compatible syntax until the pydantic pin is resolved
