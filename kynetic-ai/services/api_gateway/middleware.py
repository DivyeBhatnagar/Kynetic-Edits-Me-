"""
API Gateway — Rate Limiting Middleware.

Implements a Redis-backed sliding-window rate limiter.
Applied per client IP address to all routes.
Returns HTTP 429 Too Many Requests when the limit is exceeded.

Algorithm: sliding window counter using Redis ZADD + ZRANGEBYSCORE.
This is more accurate than a fixed-window counter, and cheaper than
a true token bucket — a good production-quality tradeoff.
"""

import time

import redis.asyncio as aioredis
import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from services.api_gateway.config import get_settings

logger = structlog.get_logger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Redis-backed sliding-window rate limiter (per client IP).

    Configuration (from APIGatewaySettings):
        rate_limit_requests_per_minute — sustained rate limit
        rate_limit_burst               — burst headroom above the limit

    Routes excluded from rate limiting:
        /healthz — internal health checks
    """

    EXCLUDED_PATHS = {"/healthz", "/docs", "/redoc", "/openapi.json"}

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self.settings = get_settings()
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = await aioredis.from_url(
                self.settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in self.EXCLUDED_PATHS:
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        allowed, remaining, reset_at = await self._check_rate_limit(client_ip)

        if not allowed:
            logger.warning(
                "rate_limit_exceeded",
                client_ip=client_ip,
                path=request.url.path,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too many requests",
                    "detail": "Rate limit exceeded. Please slow down.",
                    "retry_after_seconds": max(0, int(reset_at - time.time())),
                },
                headers={
                    "Retry-After": str(max(0, int(reset_at - time.time()))),
                    "X-RateLimit-Limit": str(self.settings.rate_limit_requests_per_minute),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(reset_at)),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.settings.rate_limit_requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(reset_at))
        return response

    def _get_client_ip(self, request: Request) -> str:
        """
        Extract client IP, respecting X-Forwarded-For from a trusted proxy.
        In production, ensure only trusted load balancers can set this header.
        """
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def _check_rate_limit(
        self, client_ip: str
    ) -> tuple[bool, int, float]:
        """
        Sliding window check for client_ip.

        Returns:
            (allowed, remaining_requests, window_reset_at_unix_timestamp)
        """
        try:
            redis = await self._get_redis()
        except Exception as exc:
            # If Redis is unavailable, fail open (allow the request) and log
            logger.error("rate_limiter_redis_error", error=str(exc))
            return True, self.settings.rate_limit_requests_per_minute, time.time() + 60

        now = time.time()
        window_seconds = 60
        window_start = now - window_seconds
        limit = self.settings.rate_limit_requests_per_minute + self.settings.rate_limit_burst
        key = f"ratelimit:gateway:{client_ip}"

        pipe = redis.pipeline()
        # Remove entries older than the window
        pipe.zremrangebyscore(key, 0, window_start)
        # Count current entries in the window
        pipe.zcard(key)
        # Add current request timestamp
        pipe.zadd(key, {str(now): now})
        # Set TTL on the key
        pipe.expire(key, window_seconds + 5)

        results = await pipe.execute()
        request_count = results[1]  # count before adding current

        allowed = request_count < limit
        remaining = max(0, limit - request_count - 1)
        reset_at = now + window_seconds

        return allowed, remaining, reset_at
