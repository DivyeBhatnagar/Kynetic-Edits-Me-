"""
Shared async httpx client wrapper for inter-service communication.
# ponytail: merged safe_get/safe_post into safe_request (saved 50 lines)
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)
DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)


@asynccontextmanager
async def get_http_client(
    base_url: str = "",
    timeout: httpx.Timeout = DEFAULT_TIMEOUT,
    extra_headers: dict | None = None,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async context manager returning a configured httpx.AsyncClient."""
    ctx = structlog.contextvars.get_contextvars()
    headers = {
        "Content-Type": "application/json",
        "X-Correlation-ID": ctx.get("correlation_id", ""),
        "X-Source-Service": ctx.get("service_name", "kynetic"),
    }
    if extra_headers:
        headers.update(extra_headers)

    async with httpx.AsyncClient(
        base_url=base_url,
        headers=headers,
        timeout=timeout,
        follow_redirects=True,
    ) as client:
        yield client


async def safe_request(
    method: str,
    url: str,
    *,
    json: Any = None,
    params: dict | None = None,
    timeout: float = 30.0,
    extra_headers: dict | None = None,
) -> httpx.Response:
    """Unified HTTP request helper with structured error handling."""
    async with get_http_client(extra_headers=extra_headers) as client:
        try:
            response = await client.request(method, url, json=json, params=params, timeout=timeout)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            logger.error("http_request_failed", url=url, status_code=exc.response.status_code, detail=exc.response.text[:500])
            raise
        except httpx.RequestError as exc:
            logger.error("http_request_error", url=url, error=str(exc))
            raise


async def safe_post(url: str, json: dict, timeout: float = 30.0, extra_headers: dict | None = None) -> httpx.Response:
    return await safe_request("POST", url, json=json, timeout=timeout, extra_headers=extra_headers)


async def safe_get(url: str, params: dict | None = None, timeout: float = 30.0, extra_headers: dict | None = None) -> httpx.Response:
    return await safe_request("GET", url, params=params, timeout=timeout, extra_headers=extra_headers)
