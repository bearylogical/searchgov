import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware

# Module-level context var so loguru and other code can read the
# current request ID without it being passed through every call.
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """Attach a unique X-Request-ID to every request and response."""

    async def dispatch(self, request, call_next):
        request_id = (
            request.headers.get("X-Request-ID") or str(uuid.uuid4())
        )
        request_id_var.set(request_id)
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
