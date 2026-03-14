# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install Python dependencies
uv sync

# Run FastAPI server (port 8081) — primary backend
uv run api_main.py

# Run NiceGUI web app (port 8080) — legacy, being retired
uv run main.py

# Lint
uv run ruff check .
uv run ruff format .

# Run tests
uv run pytest
uv run pytest tests/test_clean.py::test_clean_text   # single test

# Frontend (SvelteKit) — run from frontend/ directory
cd frontend && npm install
npm run dev        # dev server on port 5173, proxies /api → localhost:8081
npm run build      # compile to frontend/build/ (served by FastAPI)
npm run check      # TypeScript + Svelte type-check
```

## Architecture

This is a Singapore Government Directory Intelligence (SGDI) analytics platform. It ingests government employment records and exposes them through:

- **`api_main.py`** — FastAPI REST API on port 8081, docs at `/docs`
- **`frontend/`** — SvelteKit SPA (TypeScript), compiled to `frontend/build/` and served by FastAPI as static files

Both share the same singleton `graph_facade` (`TemporalGraph`) initialised via FastAPI's lifespan hook and stored on `app.state`.

> **NiceGUI (`main.py`) is being retired.** Do not add new features to it. New UI work goes in `frontend/`.

### Middleware stack (FastAPI, outermost → innermost)

```
CORSMiddleware          — origin allowlist from ALLOWED_ORIGINS env var
JWTAuthMiddleware       — validates Supabase JWT on all /api/* routes
LoggingMiddleware       — structured request/response logging (loguru)
CorrelationIDMiddleware — attaches X-Request-ID to every request/response
```

All middleware lives in `src/middleware/`. `CorrelationIDMiddleware` exposes `request_id_var` (a `ContextVar`) so loguru can include the ID in any log line without passing it explicitly.

### Core layers

**`src/app/temporal_graph.py`** — The single facade that all callers (views and API routers) use. Never bypass it to call repositories or services directly from UI/API code.

**`src/state.py`** — Creates/destroys the `TemporalGraph` instance. Called by both the FastAPI lifespan and the legacy NiceGUI startup hook. After `initialize_app_state()` runs, the facade is also stored on `app.state.facade` for use in DI.

**Repositories** (`src/repositories/`) — Thin asyncpg wrappers: `PeopleRepository`, `OrganisationsRepository`, `EmploymentRepository`. They execute SQL and return raw `dict`s.

**Services** (`src/services/`) — Business logic built on top of repositories:
- `QueryService` — career progression, colleague discovery, temporal overlaps, network snapshots
- `OrganisationService` — org hierarchy traversal, subtree at date, timeline diffs
- `GraphService` — shortest path (temporal and static), centrality metrics
- `AnalyticsService` — turnover analysis, succession patterns
- `EmploymentService` — bulk insertion with disambiguation

**`src/database/postgres/connection.py`** — `AsyncDatabaseConnection` wraps an `asyncpg` pool. All DB access goes through its `fetch()`, `fetchrow()`, `execute()`, and `transaction()` methods.

### FastAPI layer (`src/api/`)

- `src/api/__init__.py` — `create_api()` factory; mounts middleware, routers, and SPA static files
- `src/api/dependencies.py` — `get_facade(request)` DI function; reads from `request.app.state.facade`, raises 503 if not ready
- `src/api/routers/` — one file per domain: `people`, `organisations`, `graph`, `analytics`, `system`
- `src/api/schemas/` — Pydantic models using v1 syntax (`class Config: orm_mode = True`) — required because pydantic is pinned `>=1.10.22,<2`

### Frontend (`frontend/`)

SvelteKit SPA with file-based routing. Pages mirror the old NiceGUI views.

```
frontend/src/
  lib/
    api.ts        — typed fetch client wrapping /api/v1 (all routes)
    auth.ts       — Supabase JS client + session store + signIn/signOut helpers
  routes/
    +layout.svelte        — shared header/nav/footer
    +page.svelte          — home (/)
    login/+page.svelte    — sign-in form
    progression/+page.svelte   — career progression explorer
    organisation/+page.svelte  — organisation hierarchy explorer
```

The Vite dev server proxies `/api` → `http://localhost:8081` so the frontend and backend can run independently during development.

### Auth flow

1. Browser calls `supabase.auth.signInWithPassword()` via `src/lib/auth.ts`
2. Supabase returns an access token (JWT)
3. Every API call includes `Authorization: Bearer <token>`
4. `JWTAuthMiddleware` calls `supabase.auth.get_user(token)` to validate; sets `request.state.user` on success

Set `REQUIRE_AUTH=false` in `.env` to bypass JWT validation during local development.

### Key environment variables

```
POSTGRES_HOST / POSTGRES_DB / POSTGRES_PORT / POSTGRES_USER / POSTGRES_PASSWORD
SUPABASE_URL / SUPABASE_KEY
ALLOWED_ORIGINS=http://localhost:5173   # comma-separated
REQUIRE_AUTH=true                        # set false to skip JWT in dev
SESSION_SECRET=<random hex>             # NiceGUI session secret (legacy)
LOG_LEVEL=DEBUG|INFO
ENV=development                          # enables uvicorn --reload
```

See `.env.example` for the full list.

## Code conventions

- Line length: 79 characters (enforced by `ruff.toml`)
- All DB calls are `async` — never call repository or service methods synchronously
- `loguru` is used throughout — import `from loguru import logger`, not the stdlib `logging`
- Pydantic schemas must use v1-compatible syntax until the pydantic pin is resolved (`<2`)
- Middleware must not import from `src.frontend` or `nicegui` — those are legacy
