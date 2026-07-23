"""
Provisioning Service — Template Routes (Phase 6).

Public + admin endpoints for the template registry, plus the
GET /instances/{id}/web-ui endpoint for issuing short-lived web UI tokens.

Route summary:
  GET  /v1/templates                   — public: list available templates
  GET  /v1/templates/{id_or_slug}      — public: get one template
  POST /v1/templates                   — admin-only: create + enqueue scan
  GET  /v1/instances/{id}/web-ui       — protected: issue web UI token

Security:
  - Admin routes check for `role=admin` in the JWT payload.
  - Web UI tokens are short-lived (TTL from config), scoped per-instance.
  - Token revocation happens automatically on instance termination (tasks.py).
"""

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from libs.db_models.database import get_async_session
from libs.db_models.provisioning_models import InstanceStatus
from libs.db_models.template_models import TemplateStatus
from services.provisioning_service.config import get_settings
from services.provisioning_service.repository import InstanceRepository
from services.provisioning_service.template_repository import (
    TemplateRepository,
    WebUISessionRepository,
)
from services.provisioning_service.schemas import (
    CreateTemplateRequest,
    TemplateListResponse,
    TemplateResponse,
    WebUILinkResponse,
)

log = structlog.get_logger(__name__)
settings = get_settings()

template_router = APIRouter(tags=["templates"])
bearer = HTTPBearer()


# ── Auth helpers ────────────────────────────────────────────────────────────

async def _get_current_user_id(
    creds: Annotated[HTTPAuthorizationCredentials, Depends(bearer)],
) -> uuid.UUID:
    import jwt as pyjwt
    try:
        payload = pyjwt.decode(
            creds.credentials,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return uuid.UUID(payload["sub"])
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


async def _require_admin(
    creds: Annotated[HTTPAuthorizationCredentials, Depends(bearer)],
) -> uuid.UUID:
    """Validates JWT and ensures role=admin claim."""
    import jwt as pyjwt
    try:
        payload = pyjwt.decode(
            creds.credentials,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        if payload.get("role") != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin role required",
            )
        return uuid.UUID(payload["sub"])
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


# ── Public: list templates ──────────────────────────────────────────────────

@template_router.get(
    "/templates",
    response_model=TemplateListResponse,
    summary="List all available one-click launch templates",
    description=(
        "Returns all templates that have passed image scanning and are ready "
        "for one-click launch. No authentication required."
    ),
)
async def list_templates(session=Depends(get_async_session)):
    async with session.begin():
        templates = await TemplateRepository(session).get_all_available()
    return TemplateListResponse(
        items=[TemplateResponse.model_validate(t) for t in templates],
        total=len(templates),
    )


# ── Public: get one template ────────────────────────────────────────────────

@template_router.get(
    "/templates/{id_or_slug}",
    response_model=TemplateResponse,
    summary="Get a template by ID or slug",
)
async def get_template(id_or_slug: str, session=Depends(get_async_session)):
    repo = TemplateRepository(session)
    async with session.begin():
        # Try UUID first, fall back to slug
        template = None
        try:
            template_id = uuid.UUID(id_or_slug)
            template = await repo.get_by_id(template_id)
        except ValueError:
            template = await repo.get_by_slug(id_or_slug)

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    if template.status != TemplateStatus.available:
        raise HTTPException(
            status_code=404,
            detail="Template is not available",
        )
    return TemplateResponse.model_validate(template)


# ── Admin: create template ──────────────────────────────────────────────────

@template_router.post(
    "/templates",
    response_model=TemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="(Admin) Register a new template image",
    description=(
        "Creates a new template in `pending_scan` state and enqueues an "
        "image scan via the security service. Template becomes `available` "
        "only after the scan passes."
    ),
)
async def create_template(
    body: CreateTemplateRequest,
    _admin_id: Annotated[uuid.UUID, Depends(_require_admin)],
    session=Depends(get_async_session),
):
    async with session.begin():
        repo = TemplateRepository(session)
        # Ensure slug is unique
        existing = await repo.get_by_slug(body.slug)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Template with slug '{body.slug}' already exists",
            )
        template = await repo.create(
            name=body.name,
            slug=body.slug,
            description=body.description,
            base_image=body.base_image,
            required_gpu_vram_gb=body.required_gpu_vram_gb,
            required_ram_gb=body.required_ram_gb,
            required_vcpus=body.required_vcpus,
            startup_command=body.startup_command,
            exposed_web_ui_path=body.exposed_web_ui_path,
            web_ui_port=body.web_ui_port,
            icon_emoji=body.icon_emoji,
            tags=body.tags,
        )

    # Enqueue image scan (Phase 5 pipeline) — runs outside the DB transaction
    from services.provisioning_service.tasks import scan_template_image
    scan_template_image.delay(str(template.id), template.base_image)
    log.info(
        "template.scan_enqueued",
        template_id=str(template.id),
        base_image=template.base_image,
    )

    return TemplateResponse.model_validate(template)


# ── Protected: web UI link ──────────────────────────────────────────────────

@template_router.get(
    "/instances/{instance_id}/web-ui",
    response_model=WebUILinkResponse,
    summary="Get a short-lived web UI access link for a running instance",
    description=(
        "Issues a short-lived (1 hour) web UI access token for instances "
        "launched from a template that exposes a browser UI (e.g. ComfyUI, "
        "Stable Diffusion). The token is embedded in a proxy URL routed "
        "through the WireGuard relay — the raw host port is never exposed. "
        "Revoked automatically on instance termination."
    ),
)
async def get_web_ui_link(
    instance_id: uuid.UUID,
    developer_id: Annotated[uuid.UUID, Depends(_get_current_user_id)],
    session=Depends(get_async_session),
):
    async with session.begin():
        instance_repo = InstanceRepository(session)
        instance = await instance_repo.get_by_id(instance_id)

        if not instance:
            raise HTTPException(status_code=404, detail="Instance not found")
        if instance.developer_id != developer_id:
            raise HTTPException(status_code=403, detail="Forbidden")
        if instance.status != InstanceStatus.running:
            raise HTTPException(
                status_code=409,
                detail=f"Instance must be running. Current status: {instance.status.value}",
            )
        if not instance.template_id:
            raise HTTPException(
                status_code=400,
                detail="This instance was not launched from a template with a web UI",
            )

        # Fetch the template to confirm it has a web UI
        template_repo = TemplateRepository(session)
        template = await template_repo.get_by_id(instance.template_id)
        if not template or not template.web_ui_port:
            raise HTTPException(
                status_code=400,
                detail="This template does not expose a web UI",
            )

        # Issue token
        web_ui_session = await WebUISessionRepository(session).create(
            instance_id=instance_id,
            template_id=template.id,
            ttl_seconds=settings.template_web_ui_token_ttl_seconds,
        )

    # Build the proxy URL — in production this would be a dedicated proxy service
    # (e.g. Nginx + WireGuard relay). For MVP, we embed the token and the
    # WireGuard relay host so the developer can construct the URL.
    relay_host = settings.wireguard_relay_host
    proxy_path = template.exposed_web_ui_path or "/"
    web_ui_url = (
        f"https://{relay_host}/webui/{instance_id}"
        f"?token={web_ui_session.token}&path={proxy_path}"
    )

    return WebUILinkResponse(
        instance_id=instance_id,
        template_id=template.id,
        web_ui_url=web_ui_url,
        token=web_ui_session.token,
        expires_at=web_ui_session.expires_at,
        web_ui_port=template.web_ui_port,
    )
