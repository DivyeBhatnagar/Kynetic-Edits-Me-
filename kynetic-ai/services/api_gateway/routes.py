"""
API Gateway — Routing / Proxy.

Routes incoming requests to the appropriate internal service.
JWT validation happens here before proxying (protected routes only).

In Phase 1, we route /auth/* to auth_service.
Subsequent phases add routes for marketplace, wallet, provisioning, etc.
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from jose import jwt as jose_jwt

from libs.common.http_client import get_http_client
from services.api_gateway.config import get_settings

logger = structlog.get_logger(__name__)
gateway_router = APIRouter()
bearer_scheme = HTTPBearer(auto_error=False)
settings = get_settings()


# ---------------------------------------------------------------------------
# JWT validation dependency
# ---------------------------------------------------------------------------
async def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    """
    Validate the Bearer JWT.
    Returns the decoded payload if valid, raises 401 otherwise.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    try:
        payload = jose_jwt.decode(
            credentials.credentials,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )


# ---------------------------------------------------------------------------
# Generic proxy helper
# ---------------------------------------------------------------------------
async def _proxy_request(request: Request, target_url: str) -> Response:
    """
    Forward the incoming request to target_url, preserving method, body,
    and relevant headers. Returns the upstream response transparently.
    """
    method = request.method
    body = await request.body()

    # Forward a safe subset of headers (strip hop-by-hop headers)
    forward_headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in {
            "host", "content-length", "transfer-encoding", "connection"
        }
    }

    async with get_http_client() as client:
        try:
            upstream = await client.request(
                method=method,
                url=target_url,
                content=body,
                headers=forward_headers,
                timeout=30.0,
            )
        except Exception as exc:
            logger.error("proxy_upstream_error", target=target_url, error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Upstream service unavailable.",
            )

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=dict(upstream.headers),
        media_type=upstream.headers.get("content-type"),
    )


# ---------------------------------------------------------------------------
# Auth routes (Phase 1) — public routes forwarded directly
# ---------------------------------------------------------------------------
@gateway_router.api_route(
    "/auth/signup",
    methods=["POST"],
    tags=["Auth Proxy"],
    summary="Proxy: POST /auth/signup → auth_service",
)
async def proxy_auth_signup(request: Request):
    return await _proxy_request(request, f"{settings.auth_service_url}/auth/signup")


@gateway_router.api_route(
    "/auth/login",
    methods=["POST"],
    tags=["Auth Proxy"],
    summary="Proxy: POST /auth/login → auth_service",
)
async def proxy_auth_login(request: Request):
    return await _proxy_request(request, f"{settings.auth_service_url}/auth/login")


@gateway_router.api_route(
    "/auth/refresh",
    methods=["POST"],
    tags=["Auth Proxy"],
    summary="Proxy: POST /auth/refresh → auth_service",
)
async def proxy_auth_refresh(request: Request):
    return await _proxy_request(request, f"{settings.auth_service_url}/auth/refresh")


# ---------------------------------------------------------------------------
# Protected auth routes — JWT validated at gateway
# ---------------------------------------------------------------------------
@gateway_router.api_route(
    "/auth/logout",
    methods=["POST"],
    tags=["Auth Proxy"],
    summary="Proxy: POST /auth/logout → auth_service (protected)",
)
async def proxy_auth_logout(request: Request, _: dict = Depends(require_auth)):
    return await _proxy_request(request, f"{settings.auth_service_url}/auth/logout")


@gateway_router.api_route(
    "/auth/me",
    methods=["GET"],
    tags=["Auth Proxy"],
    summary="Proxy: GET /auth/me → auth_service (protected)",
)
async def proxy_auth_me(request: Request, _: dict = Depends(require_auth)):
    return await _proxy_request(request, f"{settings.auth_service_url}/auth/me")


@gateway_router.api_route(
    "/auth/phone/send-otp",
    methods=["POST"],
    tags=["Auth Proxy"],
    summary="Proxy: POST /auth/phone/send-otp → auth_service (protected)",
)
async def proxy_phone_send_otp(request: Request, _: dict = Depends(require_auth)):
    return await _proxy_request(request, f"{settings.auth_service_url}/auth/phone/send-otp")


@gateway_router.api_route(
    "/auth/phone/verify-otp",
    methods=["POST"],
    tags=["Auth Proxy"],
    summary="Proxy: POST /auth/phone/verify-otp → auth_service (protected)",
)
async def proxy_phone_verify_otp(request: Request, _: dict = Depends(require_auth)):
    return await _proxy_request(request, f"{settings.auth_service_url}/auth/phone/verify-otp")


# ---------------------------------------------------------------------------
# Host routes (Phase 2) — all protected, forwarded to host_service
# ---------------------------------------------------------------------------
@gateway_router.api_route(
    "/hosts/register",
    methods=["POST"],
    tags=["Host Proxy"],
    summary="Proxy: POST /hosts/register → host_service (protected)",
)
async def proxy_hosts_register(request: Request, _: dict = Depends(require_auth)):
    return await _proxy_request(request, f"{settings.host_service_url}/hosts/register")


@gateway_router.api_route(
    "/hosts/heartbeat",
    methods=["POST"],
    tags=["Host Proxy"],
    summary="Proxy: POST /hosts/heartbeat → host_service (no JWT — mTLS authenticated)",
)
async def proxy_hosts_heartbeat(request: Request):
    # Heartbeat uses mTLS client cert, not JWT — auth handled by host_service
    return await _proxy_request(request, f"{settings.host_service_url}/hosts/heartbeat")


@gateway_router.api_route(
    "/hosts/{host_id}",
    methods=["GET"],
    tags=["Host Proxy"],
    summary="Proxy: GET /hosts/{host_id} → host_service (protected)",
)
async def proxy_hosts_get(host_id: str, request: Request, _: dict = Depends(require_auth)):
    return await _proxy_request(request, f"{settings.host_service_url}/hosts/{host_id}")


@gateway_router.api_route(
    "/hosts/{host_id}/benchmarks",
    methods=["GET", "POST"],
    tags=["Host Proxy"],
    summary="Proxy: /hosts/{host_id}/benchmarks → host_service (protected)",
)
async def proxy_host_benchmarks(host_id: str, request: Request, _: dict = Depends(require_auth)):
    return await _proxy_request(
        request, f"{settings.host_service_url}/hosts/{host_id}/benchmarks"
    )


@gateway_router.api_route(
    "/hosts/{host_id}/benchmarks/rerun",
    methods=["POST"],
    tags=["Host Proxy"],
    summary="Proxy: POST /hosts/{host_id}/benchmarks/rerun → host_service (protected)",
)
async def proxy_host_benchmarks_rerun(
    host_id: str, request: Request, _: dict = Depends(require_auth)
):
    return await _proxy_request(
        request, f"{settings.host_service_url}/hosts/{host_id}/benchmarks/rerun"
    )


# ---------------------------------------------------------------------------
# Marketplace routes (Phase 3) — listings CRUD
# ---------------------------------------------------------------------------
@gateway_router.api_route(
    "/listings",
    methods=["POST"],
    tags=["Marketplace Proxy"],
    summary="Proxy: POST /listings → marketplace_service (protected)",
)
async def proxy_listings_create(request: Request, _: dict = Depends(require_auth)):
    return await _proxy_request(request, f"{settings.marketplace_service_url}/listings")


@gateway_router.api_route(
    "/listings",
    methods=["GET"],
    tags=["Marketplace Proxy"],
    summary="Proxy: GET /listings → marketplace_service (public browse)",
)
async def proxy_listings_browse(request: Request):
    return await _proxy_request(request, f"{settings.marketplace_service_url}/listings")


@gateway_router.api_route(
    "/listings/{listing_id}",
    methods=["GET"],
    tags=["Marketplace Proxy"],
    summary="Proxy: GET /listings/{listing_id} → marketplace_service",
)
async def proxy_listing_get(listing_id: str, request: Request):
    return await _proxy_request(
        request, f"{settings.marketplace_service_url}/listings/{listing_id}"
    )


@gateway_router.api_route(
    "/listings/{listing_id}",
    methods=["PATCH"],
    tags=["Marketplace Proxy"],
    summary="Proxy: PATCH /listings/{listing_id} → marketplace_service (protected)",
)
async def proxy_listing_update(
    listing_id: str, request: Request, _: dict = Depends(require_auth)
):
    return await _proxy_request(
        request, f"{settings.marketplace_service_url}/listings/{listing_id}"
    )


@gateway_router.api_route(
    "/listings/{listing_id}",
    methods=["DELETE"],
    tags=["Marketplace Proxy"],
    summary="Proxy: DELETE /listings/{listing_id} → marketplace_service (protected)",
)
async def proxy_listing_delete(
    listing_id: str, request: Request, _: dict = Depends(require_auth)
):
    return await _proxy_request(
        request, f"{settings.marketplace_service_url}/listings/{listing_id}"
    )


# ---------------------------------------------------------------------------
# Wallet & Billing routes (Phase 3)
# ---------------------------------------------------------------------------
@gateway_router.api_route(
    "/wallet/balance",
    methods=["GET"],
    tags=["Wallet Proxy"],
    summary="Proxy: GET /wallet/balance → wallet_billing_service (protected)",
)
async def proxy_wallet_balance(request: Request, _: dict = Depends(require_auth)):
    return await _proxy_request(
        request, f"{settings.wallet_billing_service_url}/wallet/balance"
    )


@gateway_router.api_route(
    "/wallet/transactions",
    methods=["GET"],
    tags=["Wallet Proxy"],
    summary="Proxy: GET /wallet/transactions → wallet_billing_service (protected)",
)
async def proxy_wallet_transactions(request: Request, _: dict = Depends(require_auth)):
    return await _proxy_request(
        request, f"{settings.wallet_billing_service_url}/wallet/transactions"
    )


@gateway_router.api_route(
    "/wallet/topup",
    methods=["POST"],
    tags=["Wallet Proxy"],
    summary="Proxy: POST /wallet/topup → wallet_billing_service (protected)",
)
async def proxy_wallet_topup(request: Request, _: dict = Depends(require_auth)):
    return await _proxy_request(
        request, f"{settings.wallet_billing_service_url}/wallet/topup"
    )


@gateway_router.api_route(
    "/billing/webhooks/stripe",
    methods=["POST"],
    tags=["Billing Proxy"],
    summary="Proxy: POST /billing/webhooks/stripe → wallet_billing_service (NO JWT — Stripe calls this)",
)
async def proxy_stripe_webhook(request: Request):
    # Stripe-Signature header must be forwarded — handled by _proxy_request header passthrough
    return await _proxy_request(
        request, f"{settings.wallet_billing_service_url}/billing/webhooks/stripe"
    )


# ---------------------------------------------------------------------------
# Provisioning routes (Phase 4) — instance lifecycle
# ---------------------------------------------------------------------------
@gateway_router.api_route(
    "/instances",
    methods=["POST"],
    tags=["Provisioning Proxy"],
    summary="Proxy: POST /instances → provisioning_service (protected)",
)
async def proxy_instances_launch(request: Request, _: dict = Depends(require_auth)):
    return await _proxy_request(
        request, f"{settings.provisioning_service_url}/v1/instances"
    )


@gateway_router.api_route(
    "/instances",
    methods=["GET"],
    tags=["Provisioning Proxy"],
    summary="Proxy: GET /instances → provisioning_service (protected)",
)
async def proxy_instances_list(request: Request, _: dict = Depends(require_auth)):
    return await _proxy_request(
        request, f"{settings.provisioning_service_url}/v1/instances"
    )


@gateway_router.api_route(
    "/instances/{instance_id}",
    methods=["GET"],
    tags=["Provisioning Proxy"],
    summary="Proxy: GET /instances/{id} → provisioning_service (protected)",
)
async def proxy_instance_get(
    instance_id: str, request: Request, _: dict = Depends(require_auth)
):
    return await _proxy_request(
        request, f"{settings.provisioning_service_url}/v1/instances/{instance_id}"
    )


@gateway_router.api_route(
    "/instances/{instance_id}/stop",
    methods=["POST"],
    tags=["Provisioning Proxy"],
    summary="Proxy: POST /instances/{id}/stop → provisioning_service (protected)",
)
async def proxy_instance_stop(
    instance_id: str, request: Request, _: dict = Depends(require_auth)
):
    return await _proxy_request(
        request, f"{settings.provisioning_service_url}/v1/instances/{instance_id}/stop"
    )


@gateway_router.api_route(
    "/instances/{instance_id}/start",
    methods=["POST"],
    tags=["Provisioning Proxy"],
    summary="Proxy: POST /instances/{id}/start → provisioning_service (protected)",
)
async def proxy_instance_start(
    instance_id: str, request: Request, _: dict = Depends(require_auth)
):
    return await _proxy_request(
        request, f"{settings.provisioning_service_url}/v1/instances/{instance_id}/start"
    )


@gateway_router.api_route(
    "/instances/{instance_id}/terminate",
    methods=["POST"],
    tags=["Provisioning Proxy"],
    summary="Proxy: POST /instances/{id}/terminate → provisioning_service (protected)",
)
async def proxy_instance_terminate(
    instance_id: str, request: Request, _: dict = Depends(require_auth)
):
    return await _proxy_request(
        request,
        f"{settings.provisioning_service_url}/v1/instances/{instance_id}/terminate",
    )


@gateway_router.api_route(
    "/instances/{instance_id}/connection",
    methods=["GET"],
    tags=["Provisioning Proxy"],
    summary="Proxy: GET /instances/{id}/connection → provisioning_service (protected)",
)
async def proxy_instance_connection(
    instance_id: str, request: Request, _: dict = Depends(require_auth)
):
    return await _proxy_request(
        request,
        f"{settings.provisioning_service_url}/v1/instances/{instance_id}/connection",
    )


@gateway_router.api_route(
    "/instances/{instance_id}/deletion-receipt",
    methods=["GET"],
    tags=["Provisioning Proxy"],
    summary="Proxy: GET /instances/{id}/deletion-receipt → provisioning_service (protected)",
)
async def proxy_instance_deletion_receipt(
    instance_id: str, request: Request, _: dict = Depends(require_auth)
):
    return await _proxy_request(
        request,
        f"{settings.provisioning_service_url}/v1/instances/{instance_id}/deletion-receipt",
    )

