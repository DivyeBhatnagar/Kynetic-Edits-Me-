"""
API Gateway — Redis Token-Bucket Rate Limiter.

Applied as a FastAPI middleware to all public routes.

Algorithm: token bucket with per-IP tracking.
  - Each IP gets `rpm` tokens per minute (refilled each minute)
  - Each request consumes one token
  - When tokens exhausted → 429 Too Many Requests

Route-specific limits:
  - /auth/* routes: stricter (20 RPM) to mitigate credential stuffing
  - /admin/* routes: moderate (30 RPM)
  - All other routes: 60 RPM default

Implementation uses Redis INCR + EXPIRE for atomic, lock-free counting.
The window is a rolling 60-second window per IP per route group.
"""

import time
from typing import Callable

import redis.asyncio as aioredis
import structlog
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

log = structlog.get_logger(__name__)


class RateLimitConfig:
    def __init__(self, redis_url: str, default_rpm: int = 60, burst: int = 10):
        self.redis_url = redis_url
        self.default_rpm = default_rpm
        self.burst = burst
        # Route-prefix → requests-per-minute
        self.route_limits: dict[str, int] = {
            "/auth": 20,
            "/admin": 30,
        }

    def get_limit(self, path: str) -> int:
        for prefix, limit in self.route_limits.items():
            if path.startswith(prefix):
                return limit
        return self.default_rpm


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """
    Token-bucket rate limiter middleware.

    Skipped for:
      - /health and /metrics (internal probes)
      - OPTIONS requests (CORS preflight)
    """

    def __init__(self, app, config: RateLimitConfig):
        super().__init__(app)
        self.config = config
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(
                self.config.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    def _get_client_ip(self, request: Request) -> str:
        # Respect X-Forwarded-For from trusted proxy (API gateway sits behind Nginx/LB)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"

    def _rate_limit_key(self, ip: str, path: str) -> str:
        """
        Key format: rl:{ip}:{route_group}:{minute_window}
        Minute window ensures keys auto-expire naturally.
        """
        minute = int(time.time() // 60)
        # Group by prefix for route-specific limits
        route_group = "default"
        for prefix in self.config.route_limits:
            if path.startswith(prefix):
                route_group = prefix.lstrip("/")
                break
        return f"rl:{ip}:{route_group}:{minute}"

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        # Skip rate limiting for health/metrics/CORS
        if path in ("/health", "/metrics", "/") or request.method == "OPTIONS":
            return await call_next(request)

        limit = self.config.get_limit(path)
        ip = self._get_client_ip(request)
        key = self._rate_limit_key(ip, path)

        try:
            r = await self._get_redis()
            # Atomic increment — if key doesn't exist, INCR creates it at 1
            count = await r.incr(key)
            if count == 1:
                # Set expiry on first request in the window (65s gives a small grace period)
                await r.expire(key, 65)

            # Allow a small burst above the RPM limit
            effective_limit = limit + self.config.burst

            if count > effective_limit:
                log.warning(
                    "rate_limit.exceeded",
                    ip=ip,
                    path=path,
                    count=count,
                    limit=effective_limit,
                )
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "Rate limit exceeded. Please slow down.",
                        "retry_after_seconds": 60 - int(time.time() % 60),
                    },
                    headers={
                        "Retry-After": str(60 - int(time.time() % 60)),
                        "X-RateLimit-Limit": str(limit),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(int(time.time() // 60 + 1) * 60),
                    },
                )

        except Exception as exc:
            # If Redis is unavailable, fail open (don't block legitimate traffic)
            log.error("rate_limiter.redis_error", error=str(exc), path=path)

        response = await call_next(request)

        # Annotate response with rate limit headers
        try:
            response.headers["X-RateLimit-Limit"] = str(limit)
            remaining = max(0, limit - (count if "count" in dir() else 0))
            response.headers["X-RateLimit-Remaining"] = str(remaining)
        except Exception:
            pass

        return response
