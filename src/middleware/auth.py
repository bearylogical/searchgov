import asyncio
import os

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger

# Paths that never require authentication.
_EXEMPT_EXACT = frozenset(
    {"/api/v1/system/health", "/docs", "/openapi.json", "/redoc"}
)
# Path prefixes that never require authentication (static assets, etc.).
_EXEMPT_PREFIXES = ("/_", "/favicon", "/static")


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """Validate Supabase JWTs on every /api/* route.

    The Supabase client must be stored on ``app.state.supabase`` before
    this middleware processes any requests (done in the lifespan hook).

    Set ``REQUIRE_AUTH=false`` to bypass validation in development.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Always allow exempt paths.
        if path in _EXEMPT_EXACT or any(
            path.startswith(p) for p in _EXEMPT_PREFIXES
        ):
            return await call_next(request)

        # Honour REQUIRE_AUTH=false for local dev without Supabase.
        if os.getenv("REQUIRE_AUTH", "true").lower() == "false":
            return await call_next(request)

        token = (
            request.headers.get("Authorization", "")
            .removeprefix("Bearer ")
            .strip()
        )
        if not token:
            return JSONResponse(
                {"detail": "Unauthorized"}, status_code=401
            )

        supabase = getattr(request.app.state, "supabase", None)
        if supabase is None:
            logger.error("Supabase client not initialised on app.state")
            return JSONResponse(
                {"detail": "Auth service unavailable"}, status_code=503
            )

        try:
            result = await asyncio.to_thread(
                supabase.auth.get_user, token
            )
            request.state.user = result.user
        except Exception as exc:
            logger.warning("JWT validation failed: {}", exc)
            return JSONResponse(
                {"detail": "Invalid or expired token"}, status_code=401
            )

        return await call_next(request)
