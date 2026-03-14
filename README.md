# SGDI Analytics

A platform for analysing Singapore Government Directory (SGDI) data — career histories, organisational hierarchies, and workforce patterns across the public service.

## Features

- **Career Progression** — Trace how individuals have moved across roles and organisations over time.
- **Organisation Explorer** — Browse ministry and agency hierarchies and see how they evolved at any point in time.
- **Temporal Graph** — Models employment and org structure as a graph, enabling shortest-path and centrality queries.
- **REST API** — FastAPI backend with full OpenAPI docs at `/docs`.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | SvelteKit 2 + Svelte 5 + Tailwind CSS v4 |
| Backend | FastAPI + uvicorn |
| Database | PostgreSQL + asyncpg |
| Auth | Supabase (JWT) |
| Package management | [uv](https://github.com/astral-sh/uv) |
| Containerisation | Docker (multi-stage), Docker Compose |

## Accessing the UI

### Local development

1. Start the backend:
   ```bash
   uv sync
   uv run api_main.py
   # API + UI available at http://localhost:8081
   ```

2. (Optional) Run the frontend dev server for hot-reload:
   ```bash
   cd frontend
   npm install
   npm run dev
   # Frontend at http://localhost:5173 (proxies /api → localhost:8081)
   ```

### Docker (recommended for deployment)

```bash
docker compose up --build
# UI + API available at http://localhost:8081
```

### Pages

| URL | Description |
|---|---|
| `/` | Dashboard with live stats |
| `/progression` | Career progression explorer |
| `/organisation` | Organisation hierarchy explorer |
| `/login` | Sign in |
| `/docs` | OpenAPI / Swagger UI |

## Setup

### Prerequisites

- Python 3.11
- Node.js 22+
- PostgreSQL (plain, no extensions required)
- [uv](https://github.com/astral-sh/uv)
- Supabase project (for auth)

### Environment variables

Copy `.env.example` and fill in your values:

```bash
cp .env.example .env
```

Key variables:

```
POSTGRES_HOST=localhost
POSTGRES_DB=searchgov
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=password

SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key

ALLOWED_ORIGINS=http://localhost:5173   # dev only; leave empty in production
REQUIRE_AUTH=true                        # set false to skip JWT locally
```

### Data ingestion

Run the notebooks in order to populate the database:

1. `notebooks/cleaning.ipynb` — cleans raw SGDI data → `tenure.parquet`, `orgs.parquet`
2. `notebooks/graph_ingestion.ipynb` — ingests cleaned data into PostgreSQL

## Project structure

```
.
├── api_main.py          # FastAPI entry point (port 8081)
├── frontend/            # SvelteKit SPA
│   └── src/
│       ├── lib/         # api.ts, auth.ts
│       └── routes/      # +page.svelte files (/, /progression, /organisation, /login)
├── src/
│   ├── api/             # FastAPI routers, schemas, dependencies
│   ├── app/             # TemporalGraph facade
│   ├── database/        # asyncpg connection + schema
│   ├── middleware/       # JWT auth, logging, correlation ID
│   ├── repositories/    # SQL access layer
│   └── services/        # Business logic
├── notebooks/           # Data cleaning + ingestion
├── tests/
├── Dockerfile           # Multi-stage: Node builds SPA → Python serves it
├── docker-compose.yml
└── pyproject.toml
```

## Development commands

```bash
# Backend
uv sync
uv run ruff check .
uv run ruff format .
uv run pytest

# Frontend
cd frontend
npm run dev        # dev server with HMR
npm run build      # compile to frontend/build/
npm run check      # TypeScript + Svelte type-check
```
