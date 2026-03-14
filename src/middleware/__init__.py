"""Middleware package.

FastAPI / Starlette middleware:
  - CorrelationIDMiddleware  — attaches X-Request-ID to every request
  - LoggingMiddleware        — structured request/response logging
  - JWTAuthMiddleware        — validates Supabase JWTs on /api/* routes

NiceGUI middleware (legacy, used by main.py only):
  - AuthMiddleware           — import from src.middleware.nicegui_auth;
                               NOT re-exported here to avoid a hard nicegui
                               dependency when the FastAPI app starts.
"""

from src.middleware.correlation import (
    CorrelationIDMiddleware,
    request_id_var,
)
from src.middleware.request_logging import LoggingMiddleware
from src.middleware.auth import JWTAuthMiddleware

__all__ = [
    "CorrelationIDMiddleware",
    "LoggingMiddleware",
    "JWTAuthMiddleware",
    "request_id_var",
]
