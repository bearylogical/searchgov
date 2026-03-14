"""Legacy NiceGUI auth middleware.

Used only by main.py (the NiceGUI server). Kept separate so that importing
src.middleware in a FastAPI-only context does not pull in nicegui.
"""

from fastapi import Request
from fastapi.responses import RedirectResponse
from nicegui import app as _nicegui_app
from starlette.middleware.base import BaseHTTPMiddleware

_UNRESTRICTED_ROUTES = {"/login", "/"}


class AuthMiddleware(BaseHTTPMiddleware):
    """Restrict access to all NiceGUI pages; redirect to /login."""

    async def dispatch(self, request: Request, call_next):
        if not _nicegui_app.storage.user.get("is_authenticated", False):
            if (
                not request.url.path.startswith("/_nicegui")
                and request.url.path not in _UNRESTRICTED_ROUTES
            ):
                return RedirectResponse(
                    f"/login?redirect_to={request.url.path}"
                )
        return await call_next(request)
