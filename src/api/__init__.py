import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from supabase import create_client
from loguru import logger

from src.state import initialize_app_state, shutdown_app_state
from src import state as _state
from src.middleware import (
    CorrelationIDMiddleware,
    LoggingMiddleware,
    JWTAuthMiddleware,
)
from src.api.routers.people import router as people_router
from src.api.routers.organisations import router as orgs_router
from src.api.routers.graph import router as graph_router
from src.api.routers.analytics import router as analytics_router
from src.api.routers.system import router as system_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup ---
    await initialize_app_state()
    # Expose facade on app.state so middleware and DI can reach it
    # without importing a mutable global.
    app.state.facade = _state.graph_facade

    # Initialise Supabase client for JWTAuthMiddleware.
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    if supabase_url and supabase_key:
        try:
            app.state.supabase = create_client(supabase_url, supabase_key)
            logger.info("Supabase client initialised.")
        except Exception as exc:
            logger.error("Failed to initialise Supabase client: {}", exc)
            app.state.supabase = None
    else:
        logger.warning(
            "SUPABASE_URL / SUPABASE_KEY not set — auth middleware "
            "will reject all requests unless REQUIRE_AUTH=false."
        )
        app.state.supabase = None

    yield

    # --- shutdown ---
    await shutdown_app_state()
    app.state.facade = None


def create_api() -> FastAPI:
    app = FastAPI(
        title="SGDI Analytics API",
        version="1.0.0",
        lifespan=lifespan,
    )

    # ------------------------------------------------------------------
    # Middleware (outermost → innermost execution order)
    # add_middleware() wraps in reverse, so list here is outside-in.
    # ------------------------------------------------------------------
    allowed_origins = [
        o.strip()
        for o in os.getenv(
            "ALLOWED_ORIGINS", "http://localhost:5173"
        ).split(",")
        if o.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )
    app.add_middleware(JWTAuthMiddleware)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(CorrelationIDMiddleware)

    # ------------------------------------------------------------------
    # Routers
    # ------------------------------------------------------------------
    app.include_router(
        people_router, prefix="/api/v1/people", tags=["people"]
    )
    app.include_router(
        orgs_router, prefix="/api/v1/organisations", tags=["organisations"]
    )
    app.include_router(
        graph_router, prefix="/api/v1/graph", tags=["graph"]
    )
    app.include_router(
        analytics_router, prefix="/api/v1/analytics", tags=["analytics"]
    )
    app.include_router(
        system_router, prefix="/api/v1/system", tags=["system"]
    )

    # ------------------------------------------------------------------
    # SPA static files — served after all API routes.
    # Only mounted when the build directory exists so the API starts
    # cleanly during development before the frontend is built.
    # ------------------------------------------------------------------
    spa_dir = os.path.join(
        os.path.dirname(__file__), "..", "..", "frontend", "build"
    )
    if os.path.isdir(spa_dir):
        app.mount(
            "/", StaticFiles(directory=spa_dir, html=True), name="spa"
        )
        logger.info("Serving SPA from {}", spa_dir)

    return app
