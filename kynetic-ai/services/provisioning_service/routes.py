"""
Provisioning Service — API Routes.

All instance lifecycle endpoints. Developers interact with instances
exclusively through these routes (proxied by the API Gateway).

Auth: All routes require a valid JWT (require_auth dependency).
"""

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from libs.db_models.database import get_async_session
from libs.db_models.provisioning_models import InstanceStatus
from services.provisioning_service.billing_watcher import start_billing, stop_billing
from services.provisioning_service.repository import (
    IllegalTransitionError,
    InstanceRepository,
    SSHSessionRepository,
    SecureDeletionRepository,
)
from services.provisioning_service.scheduler import (
    HostUnreachableError,
    InsufficientBalanceError,
    ListingUnavailableError,
    SchedulerError,
    schedule_instance,
)
from services.provisioning_service.schemas import (
    ConnectionInfo,
    DeletionReceiptResponse,
    InstanceListResponse,
    InstanceResponse,
    LaunchRequest,
    ProvisioningCallback,
    StopRequest,
    TerminateRequest,
)
from services.provisioning_service.ssh_keys import (
    build_ssh_command,
    decrypt_private_key,
    key_expiry_time,
)
from services.provisioning_service.wireguard import resolve_ssh_host
from services.provisioning_service.tasks import (
    stop_instance,
    terminate_instance,
)
from services.provisioning_service.config import get_settings

log = structlog.get_logger(__name__)
settings = get_settings()

provisioning_router = APIRouter(prefix="/instances", tags=["instances"])
callback_router = APIRouter(tags=["agent-callbacks"])

bearer = HTTPBearer()


# ── Auth helper ────────────────────────────────────────────────────────────

async def _get_current_user_id(
    creds: Annotated[HTTPAuthorizationCredentials, Depends(bearer)],
) -> uuid.UUID:
    """
    Validates the JWT and returns the developer's user_id.
    Reuses the same JWT secret as auth_service.
    """
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


# ── Launch ─────────────────────────────────────────────────────────────────

@provisioning_router.post(
    "",
    response_model=InstanceResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Launch a compute instance",
    description=(
        "Validates wallet balance, places a hold, and asynchronously provisions "
        "the instance on the selected host. Returns immediately with status=pending."
    ),
)
async def launch_instance(
    body: LaunchRequest,
    developer_id: Annotated[uuid.UUID, Depends(_get_current_user_id)],
    creds: Annotated[HTTPAuthorizationCredentials, Depends(bearer)],
    session=Depends(get_async_session),
):
    instance_repo = InstanceRepository(session)
    try:
        async with session.begin():
            instance_id = await schedule_instance(
                listing_id=body.listing_id,
                developer_id=developer_id,
                auth_token=creds.credentials,
                instance_repo=instance_repo,
                template_id=body.template_id,
            )
    except InsufficientBalanceError as exc:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={"code": exc.code, "message": str(exc)},
        )
    except ListingUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": str(exc)},
        )
    except HostUnreachableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": exc.code, "message": str(exc)},
        )
    except SchedulerError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": str(exc)},
        )

    async with session.begin():
        instance = await instance_repo.get_by_id(instance_id)
    return InstanceResponse.model_validate(instance)


# ── Get instance ───────────────────────────────────────────────────────────

@provisioning_router.get(
    "/{instance_id}",
    response_model=InstanceResponse,
    summary="Get instance status",
)
async def get_instance(
    instance_id: uuid.UUID,
    developer_id: Annotated[uuid.UUID, Depends(_get_current_user_id)],
    session=Depends(get_async_session),
):
    async with session.begin():
        instance = await InstanceRepository(session).get_by_id(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")
    if instance.developer_id != developer_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return InstanceResponse.model_validate(instance)


# ── List instances ─────────────────────────────────────────────────────────

@provisioning_router.get(
    "",
    response_model=InstanceListResponse,
    summary="List your instances",
)
async def list_instances(
    developer_id: Annotated[uuid.UUID, Depends(_get_current_user_id)],
    status_filter: str | None = None,
    page: int = 1,
    page_size: int = 20,
    session=Depends(get_async_session),
):
    status_enum = None
    if status_filter:
        try:
            status_enum = InstanceStatus(status_filter)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status_filter}")

    async with session.begin():
        items, total = await InstanceRepository(session).get_by_developer(
            developer_id, status=status_enum, page=page, page_size=page_size
        )
    return InstanceListResponse(
        items=[InstanceResponse.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )


# ── Stop ───────────────────────────────────────────────────────────────────

@provisioning_router.post(
    "/{instance_id}/stop",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Stop (suspend) a running instance",
)
async def stop_instance_route(
    instance_id: uuid.UUID,
    body: StopRequest,
    developer_id: Annotated[uuid.UUID, Depends(_get_current_user_id)],
    session=Depends(get_async_session),
):
    async with session.begin():
        instance = await InstanceRepository(session).get_by_id(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")
    if instance.developer_id != developer_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if instance.status != InstanceStatus.running:
        raise HTTPException(
            status_code=409,
            detail=f"Instance must be running to stop. Current status: {instance.status.value}",
        )
    stop_instance.delay(str(instance_id))
    return {"message": "Stop initiated", "instance_id": str(instance_id)}


# ── Start (resume from stopped) ────────────────────────────────────────────

@provisioning_router.post(
    "/{instance_id}/start",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Resume a stopped instance",
)
async def start_instance_route(
    instance_id: uuid.UUID,
    developer_id: Annotated[uuid.UUID, Depends(_get_current_user_id)],
    session=Depends(get_async_session),
):
    async with session.begin():
        repo = InstanceRepository(session)
        instance = await repo.get_by_id(instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail="Instance not found")
        if instance.developer_id != developer_id:
            raise HTTPException(status_code=403, detail="Forbidden")
        if instance.status != InstanceStatus.stopped:
            raise HTTPException(
                status_code=409,
                detail=f"Instance must be stopped to start. Current status: {instance.status.value}",
            )
        try:
            await repo.transition_state(instance_id, InstanceStatus.running)
        except IllegalTransitionError as exc:
            raise HTTPException(status_code=409, detail=str(exc))

    start_billing(instance_id)
    return {"message": "Instance resumed", "instance_id": str(instance_id)}


# ── Terminate ──────────────────────────────────────────────────────────────

@provisioning_router.post(
    "/{instance_id}/terminate",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Terminate an instance (irreversible)",
)
async def terminate_instance_route(
    instance_id: uuid.UUID,
    body: TerminateRequest,
    developer_id: Annotated[uuid.UUID, Depends(_get_current_user_id)],
    session=Depends(get_async_session),
):
    async with session.begin():
        instance = await InstanceRepository(session).get_by_id(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")
    if instance.developer_id != developer_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if instance.status == InstanceStatus.terminated:
        raise HTTPException(status_code=409, detail="Instance already terminated")

    terminate_instance.delay(str(instance_id), body.reason or "user")
    return {"message": "Termination initiated", "instance_id": str(instance_id)}


# ── SSH Connection info ────────────────────────────────────────────────────

@provisioning_router.get(
    "/{instance_id}/connection",
    response_model=ConnectionInfo,
    summary="Get SSH connection info for a running instance",
)
async def get_connection(
    instance_id: uuid.UUID,
    developer_id: Annotated[uuid.UUID, Depends(_get_current_user_id)],
    session=Depends(get_async_session),
):
    async with session.begin():
        instance = await InstanceRepository(session).get_by_id(instance_id)
        ssh_session = await SSHSessionRepository(session).get_by_instance(instance_id)

    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")
    if instance.developer_id != developer_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if instance.status not in (InstanceStatus.running, InstanceStatus.stopping):
        raise HTTPException(
            status_code=409,
            detail=f"Instance is not running. Status: {instance.status.value}",
        )
    if not ssh_session or not ssh_session.private_key_encrypted:
        raise HTTPException(status_code=404, detail="SSH session not available")

    # Decrypt private key (returned to developer once; treat as secret)
    private_key_pem = decrypt_private_key(ssh_session.private_key_encrypted)

    # Resolve SSH host (direct IP or WireGuard relay)
    use_relay = instance.public_ip is None
    ssh_host = resolve_ssh_host(
        public_ip=instance.public_ip,
        wireguard_ip=instance.wireguard_ip,
        use_relay=use_relay,
    )

    ssh_command = build_ssh_command(
        ssh_host=ssh_host,
        ssh_port=instance.ssh_port,
    )

    return ConnectionInfo(
        instance_id=instance_id,
        status=instance.status,
        ssh_host=ssh_host,
        ssh_port=instance.ssh_port,
        private_key_pem=private_key_pem,
        public_key=ssh_session.public_key,
        ssh_command=ssh_command,
        key_expires_at=key_expiry_time(ssh_session.issued_at),
    )


# ── Deletion receipt ───────────────────────────────────────────────────────

@provisioning_router.get(
    "/{instance_id}/deletion-receipt",
    response_model=DeletionReceiptResponse,
    summary="Fetch the secure deletion audit receipt (terminated instances only)",
)
async def get_deletion_receipt(
    instance_id: uuid.UUID,
    developer_id: Annotated[uuid.UUID, Depends(_get_current_user_id)],
    session=Depends(get_async_session),
):
    async with session.begin():
        instance = await InstanceRepository(session).get_by_id(instance_id)
        receipt = await SecureDeletionRepository(session).get_by_instance(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")
    if instance.developer_id != developer_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if not receipt:
        raise HTTPException(status_code=404, detail="No deletion receipt yet")
    return DeletionReceiptResponse.model_validate(receipt)


# ── Agent callback (internal, mTLS protected at infra level) ──────────────

@callback_router.post(
    "/instances/callback",
    status_code=status.HTTP_200_OK,
    summary="Host agent callback (internal only — not exposed via API Gateway)",
    include_in_schema=False,
)
async def agent_callback(
    body: ProvisioningCallback,
    session=Depends(get_async_session),
):
    """
    Receives lifecycle events from host agents.
    This endpoint is NOT proxied through the API Gateway —
    it is only reachable on the internal Docker network.
    """
    log.info(
        "agent_callback.received",
        instance_id=str(body.instance_id),
        event=body.event,
    )
    async with session.begin():
        repo = InstanceRepository(session)
        instance = await repo.get_by_id(body.instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail="Instance not found")

        if body.event == "provisioning_complete":
            await repo.transition_state(
                body.instance_id,
                InstanceStatus.running,
                firecracker_vm_id=body.firecracker_vm_id,
                container_id=body.container_id,
            )
            start_billing(body.instance_id)

        elif body.event == "deletion_verified" and body.deletion_hash:
            deletion_repo = SecureDeletionRepository(session)
            existing = await deletion_repo.get_by_instance(body.instance_id)
            if not existing:
                await deletion_repo.create(
                    instance_id=body.instance_id,
                    method=body.deletion_method or "agent_reported",
                    agent_confirmation_hash=body.deletion_hash,
                    agent_payload=body.deletion_payload,
                )

        elif body.event == "failed":
            if instance.status not in (InstanceStatus.terminated, InstanceStatus.failed):
                await repo.transition_state(body.instance_id, InstanceStatus.failed)

    return {"status": "acknowledged"}
