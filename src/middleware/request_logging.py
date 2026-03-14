import time

from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger

from src.middleware.correlation import request_id_var


class LoggingMiddleware(BaseHTTPMiddleware):
    """Log method, path, status, and duration for every request."""

    async def dispatch(self, request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "{method} {path} {status} {duration:.1f}ms [{rid}]",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration=duration_ms,
            rid=request_id_var.get(),
        )
        return response
