"""
Correlation ID middleware for FastAPI services.

Injects a unique request_id into structlog contextvars on every request,
so every log line emitted during that request automatically carries the ID.
This enables cross-service log correlation when the ID is propagated via headers.
"""

import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

CORRELATION_HEADER = "X-Correlation-ID"
REQUEST_ID_HEADER = "X-Request-ID"


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """
    Extracts or generates a correlation ID per request and:
    1. Binds it to structlog contextvars (auto-injected into all log lines).
    2. Forwards it in the response headers for client-side tracing.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        # Prefer an inbound correlation ID (e.g., from the API Gateway)
        correlation_id = request.headers.get(CORRELATION_HEADER) or str(uuid.uuid4())
        request_id = str(uuid.uuid4())

        # Bind both IDs to structlog's contextvars so every log line in this
        # request automatically carries them — no manual passing required.
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            correlation_id=correlation_id,
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        response = await call_next(request)
        response.headers[CORRELATION_HEADER] = correlation_id
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
