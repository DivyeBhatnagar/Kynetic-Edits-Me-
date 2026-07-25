"""
Provisioning Service — Exception Handlers (Phase 27).

Maps `InstanceValidationError` error codes to appropriate HTTP status codes
and standardized JSON error responses.

Register via:
    from services.provisioning_service.exception_handlers import register_exception_handlers
    register_exception_handlers(app)

Error code → HTTP status mapping:

    WALLET_NOT_FOUND        → 402 Payment Required
    INSUFFICIENT_BALANCE    → 402 Payment Required
    LISTING_NOT_FOUND       → 404 Not Found
    LISTING_UNAVAILABLE     → 409 Conflict
    HOST_NOT_FOUND          → 404 Not Found
    HOST_NOT_VERIFIED       → 409 Conflict
    HOST_NOT_IDLE           → 409 Conflict
    PERMISSION_DENIED       → 403 Forbidden
    (any other code)        → 422 Unprocessable Entity (fallback)
"""

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from services.provisioning_service.validators import InstanceValidationError

log = structlog.get_logger(__name__)

# ── Code → HTTP status mapping ─────────────────────────────────────────────

_CODE_TO_STATUS: dict[str, int] = {
    "WALLET_NOT_FOUND":      402,
    "INSUFFICIENT_BALANCE":  402,
    "LISTING_NOT_FOUND":     404,
    "LISTING_UNAVAILABLE":   409,
    "HOST_NOT_FOUND":        404,
    "HOST_NOT_VERIFIED":     409,
    "HOST_NOT_IDLE":         409,
    "PERMISSION_DENIED":     403,
}

_DEFAULT_STATUS = 422  # Unprocessable Entity for unknown codes


# ── Handler function ───────────────────────────────────────────────────────

async def _instance_validation_error_handler(
    request: Request,
    exc: InstanceValidationError,
) -> JSONResponse:
    """
    Convert an InstanceValidationError into a structured JSON HTTP response.

    Response body format:
        {
            "error": {
                "code": "INSUFFICIENT_BALANCE",
                "message": "Insufficient balance. Required: 1.500000 USD, available: 0.000000 USD."
            }
        }
    """
    http_status = _CODE_TO_STATUS.get(exc.code, _DEFAULT_STATUS)

    log.warning(
        "provisioning.validation_rejected",
        code=exc.code,
        message=exc.message,
        http_status=http_status,
        path=str(request.url),
    )

    return JSONResponse(
        status_code=http_status,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
            }
        },
    )


# ── Registration helper ────────────────────────────────────────────────────

def register_exception_handlers(app: FastAPI) -> None:
    """
    Attach all provisioning exception handlers to the FastAPI app.

    Call this once in `main.py` after creating the FastAPI instance:

        app = FastAPI(...)
        register_exception_handlers(app)
    """
    app.add_exception_handler(
        InstanceValidationError,
        _instance_validation_error_handler,  # type: ignore[arg-type]
    )
    log.info("exception_handlers.registered", handlers=["InstanceValidationError"])
