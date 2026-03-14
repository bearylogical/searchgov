"""Middleware package.

FastAPI / Starlette middleware:
  - CorrelationIDMiddleware  — attaches X-Request-ID to every request
  - LoggingMiddleware        — structured request/response logging
  - JWTAuthMiddleware        — validates Supabase JWTs on /api/* routes

NiceGUI middleware (legacy, used by main.py only):
  - AuthMiddleware           — redirects unauthenticated NiceGUI users
"""

from src.middleware.correlation import (
    CorrelationIDMiddleware,
    request_id_var,
)
from src.middleware.request_logging import LoggingMiddleware
from src.middleware.auth import JWTAuthMiddleware

# ---------------------------------------------------------------------------
# Legacy NiceGUI auth middleware — kept until NiceGUI is retired.
# ---------------------------------------------------------------------------
from typing import Optional

from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from nicegui import app as _nicegui_app

_unrestricted_routes = {"/login", "/"}


class AuthMiddleware(BaseHTTPMiddleware):
    """Restrict access to all NiceGUI pages; redirect to /login."""

    async def dispatch(self, request: Request, call_next):
        if not _nicegui_app.storage.user.get("is_authenticated", False):
            if (
                not request.url.path.startswith("/_nicegui")
                and request.url.path not in _unrestricted_routes
            ):
                return RedirectResponse(
                    f"/login?redirect_to={request.url.path}"
                )
        return await call_next(request)


__all__ = [
    "CorrelationIDMiddleware",
    "LoggingMiddleware",
    "JWTAuthMiddleware",
    "AuthMiddleware",
    "request_id_var",
]
