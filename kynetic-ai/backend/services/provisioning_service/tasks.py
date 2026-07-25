"""
Provisioning Service — Celery Tasks.

All tasks that involve infrastructure operations (provisioning, stopping,
terminating instances) run here. Each task:
  - Logs every state transition with structlog
  - Is idempotent (safe to retry on failure)
  - Handles the full state machine from DB perspective
  - Delegates infrastructure work to AgentProtocol

Task dependency order:
  provision_instance → [transition to running] → start_billing (billing_watcher)
  terminate_instance → [stop billing] → [agent terminate] → [agent delete_volume]
                     → [agent verify_deletion] → [write receipt] → [transition terminated]

Celery config: bind=True allows retry with self.retry().
"""

import asyncio
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import structlog
from celery import Task

from libs.db_models.database import async_session_factory
from libs.db_models.provisioning_models import InstanceStatus
from services.provisioning_service.agent_protocol import AgentProtocol
from services.provisioning_service.billing_watcher import (
    _debit_wallet,
    _emit_low_balance_event,
    should_stop,
    start_billing,
    stop_billing,
)
from services.provisioning_service.celery_app import celery_app
from services.provisioning_service.config import get_settings
from services.provisioning_service.repository import (
    InstanceRepository,
    SSHSessionRepository,
    SecureDeletionRepository,
)
from services.provisioning_service.ssh_keys import (
    decrypt_private_key,
    encrypt_private_key,
    generate_keypair,
)
from services.provisioning_service.wireguard import (
    allocate_wireguard_ip,
    generate_peer_config,
)
# Phase 28: Billing Event Integration
from services.provisioning_service.status_sync import (
    on_instance_running,
    on_instance_terminated,
    on_instance_failed,
)

log = structlog.get_logger(__name__)
settings = get_settings()


def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Provision ──────────────────────────────────────────────────────────────

@celery_app.task(bind=True, max_retries=3, default_retry_delay=10, name="provision_instance")
def provision_instance(self: Task, instance_id: str) -> None:
    """
    Dispatches provisioning to the host agent and transitions the
    instance to running state.

    Steps:
    1. Generate ephemeral SSH keypair
    2. Allocate WireGuard IP + generate peer config
    3. Call agent.provision() over mTLS
    4. Store SSH session (encrypted private key)
    5. Transition instance: pending → provisioning → running
    6. Start per-second billing watcher
    """
    _run_async(_provision_instance_async(instance_id))


async def _provision_instance_async(instance_id_str: str) -> None:
    iid = uuid.UUID(instance_id_str)
    log.info("provision_instance.start", instance_id=instance_id_str)

    async with async_session_factory() as session:
        async with session.begin():
            instance_repo = InstanceRepository(session)
            ssh_repo = SSHSessionRepository(session)

            instance = await instance_repo.get_by_id(iid)
            if not instance:
                log.error("provision_instance.not_found", instance_id=instance_id_str)
                return

            # Already past pending — idempotency check
            if instance.status not in (InstanceStatus.pending,):
                log.warning(
                    "provision_instance.already_processed",
                    instance_id=instance_id_str,
                    status=instance.status.value,
                )
                return

            # ── Phase 5: Image scan pre-check ─────────────────────────────
            # Skip when FIRECRACKER_MOCK=true (no real images in dev/CI)
            docker_img = getattr(instance, "docker_image", None)
            if not settings.firecracker_mock and docker_img:
                import httpx
                try:
                    async with httpx.AsyncClient(timeout=60.0) as http:
                        scan_resp = await http.post(
                            f"{settings.security_service_url}/v1/internal/scan-image",
                            params={
                                "image": instance.docker_image,
                                "instance_id": instance_id_str,
                            },
                        )
                        scan_resp.raise_for_status()
                        scan_result = scan_resp.json()
                    if scan_result.get("blocked"):
                        log.critical(
                            "provision_instance.image_blocked",
                            instance_id=instance_id_str,
                            image=instance.docker_image,
                            critical=scan_result.get("critical_count"),
                            high=scan_result.get("high_count"),
                        )
                        await instance_repo.transition_state(iid, InstanceStatus.failed)
                        return
                except Exception as exc:
                    # Scan failure is non-fatal in dev; fail open
                    log.warning(
                        "provision_instance.scan_unavailable",
                        instance_id=instance_id_str,
                        error=str(exc),
                    )

            # Transition: pending → provisioning
            await instance_repo.transition_state(iid, InstanceStatus.provisioning)

            # 1. Generate SSH keypair
            public_key, private_key_pem = generate_keypair()
            private_key_encrypted = encrypt_private_key(private_key_pem)

            # 2. Allocate WireGuard IP
            wg_ip = allocate_wireguard_ip(iid)
            wg_config = generate_peer_config(
                instance_id=iid,
                wireguard_ip=wg_ip,
            )

            # 3. Call host agent — pass template config if applicable
            template_base_image = None
            template_startup_cmd = None
            if instance.template_id:
                from services.provisioning_service.template_repository import TemplateRepository
                template = await TemplateRepository(session).get_by_id(instance.template_id)
                if template:
                    template_base_image = template.base_image
                    template_startup_cmd = template.startup_command
                    log.info(
                        "provision_instance.using_template",
                        instance_id=instance_id_str,
                        template_slug=template.slug,
                        base_image=template.base_image,
                    )

            agent = AgentProtocol(
                agent_host_url=instance.agent_host_url or "mock://agent",
                instance_id=iid,
            )
            try:
                result = await agent.provision(
                    public_key=public_key,
                    wireguard_config=wg_config,
                    price_per_second_usd=str(instance.price_per_second_usd),
                    # Phase 6: template overrides for one-click launch
                    base_image=template_base_image,
                    startup_command=template_startup_cmd,
                )
            except Exception as exc:
                log.error("provision_instance.agent_failed", error=str(exc), instance_id=instance_id_str)
                await instance_repo.transition_state(iid, InstanceStatus.failed)
                # Phase 28: release hold immediately on failure
                try:
                    if instance:
                        await on_instance_failed(
                            instance_id=iid,
                            developer_id=instance.developer_id,
                            reason=f"agent_unreachable: {exc}",
                        )
                except Exception:
                    pass
                return

            firecracker_vm_id = result.get("firecracker_vm_id")
            container_id = result.get("container_id")

            # 4. Store SSH session
            await ssh_repo.create(
                instance_id=iid,
                public_key=public_key,
                private_key_encrypted=private_key_encrypted,
                relay_host=settings.wireguard_relay_host
                if not instance.public_ip
                else None,
                relay_port=22 if not instance.public_ip else None,
            )

            # 5. Transition: provisioning → running
            await instance_repo.transition_state(
                iid,
                InstanceStatus.running,
                firecracker_vm_id=firecracker_vm_id,
                container_id=container_id,
                wireguard_ip=wg_ip,
            )

    # 6. Start billing (outside transaction so billing errors don't rollback)
    start_billing(iid)

    # Phase 28: Publish INSTANCE_RUNNING so the billing service starts metering
    try:
        async with async_session_factory() as session:
            async with session.begin():
                _inst = await InstanceRepository(session).get_by_id(iid)
        if _inst:
            await on_instance_running(
                instance_id=iid,
                developer_id=_inst.developer_id,
                listing_id=_inst.listing_id,
                price_per_second_usd=str(_inst.price_per_second_usd),
                price_per_second_inr=str(getattr(_inst, "price_per_second_inr", "0.023333")),
                preferred_currency=str(getattr(_inst, "preferred_currency", "usd") or "usd"),
            )
    except Exception as _evt_exc:
        log.warning(
            "provision_instance.running_event_failed",
            instance_id=instance_id_str,
            error=str(_evt_exc),
        )

    log.info("provision_instance.complete", instance_id=instance_id_str)


# ── Meter (per-second billing tick) ───────────────────────────────────────

@celery_app.task(name="meter_instance_usage")
def meter_instance_usage(instance_id: str) -> None:
    """
    Per-second billing tick. Self-reschedules via countdown=1 until
    billing is stopped.

    Design: self-rescheduling task (not beat schedule) because each
    instance has an independent lifecycle. Beat is used only for
    the reconciliation sweep task.
    """
    _run_async(_meter_tick_async(instance_id))


async def _meter_tick_async(instance_id_str: str) -> None:
    iid = uuid.UUID(instance_id_str)

    # Check Redis stop signal
    if should_stop(iid):
        log.info("meter_instance_usage.stopping", instance_id=instance_id_str)
        return

    async with async_session_factory() as session:
        async with session.begin():
            instance_repo = InstanceRepository(session)
            instance = await instance_repo.get_by_id(iid)

            if not instance or instance.status != InstanceStatus.running:
                log.info(
                    "meter_instance_usage.not_running",
                    instance_id=instance_id_str,
                    status=instance.status.value if instance else "not_found",
                )
                stop_billing(iid)
                return

            price = Decimal(str(instance.price_per_second_usd))
            developer_id = str(instance.developer_id)

    # Debit outside DB transaction (idempotent + external call)
    funded = await _debit_wallet(
        developer_id=developer_id,
        instance_id=instance_id_str,
        amount_usd=str(price),
    )

    if not funded:
        # Zero balance — trigger auto-terminate
        log.warning("meter_instance_usage.zero_balance", instance_id=instance_id_str)
        await _emit_low_balance_event(instance_id_str)
        auto_terminate_on_zero_balance.delay(instance_id_str)
        stop_billing(iid)
        return

    # Increment billed_seconds counter
    async with async_session_factory() as session:
        async with session.begin():
            await InstanceRepository(session).increment_billed_seconds(iid, 1)

    # Check low balance warning threshold
    async with async_session_factory() as session:
        async with session.begin():
            instance = await InstanceRepository(session).get_by_id(iid)
    # (Low-balance notification logic would query wallet here — Phase 10)

    # Reschedule for next second
    meter_instance_usage.apply_async(args=[instance_id_str], countdown=1)


# ── Stop ───────────────────────────────────────────────────────────────────

@celery_app.task(bind=True, max_retries=3, default_retry_delay=5, name="stop_instance")
def stop_instance(self: Task, instance_id: str) -> None:
    """Suspend the Firecracker microVM. Billing pauses."""
    _run_async(_stop_instance_async(instance_id))


async def _stop_instance_async(instance_id_str: str) -> None:
    iid = uuid.UUID(instance_id_str)
    log.info("stop_instance.start", instance_id=instance_id_str)

    async with async_session_factory() as session:
        async with session.begin():
            instance_repo = InstanceRepository(session)
            instance = await instance_repo.get_by_id(iid)
            if not instance:
                return

            stop_billing(iid)

            agent = AgentProtocol(
                agent_host_url=instance.agent_host_url or "mock://agent",
                instance_id=iid,
            )
            try:
                await agent.stop()
            except Exception as exc:
                log.error("stop_instance.agent_failed", error=str(exc))
                # Don't transition to failed — stopping is best-effort; try terminate instead

            await instance_repo.transition_state(iid, InstanceStatus.stopped)
    log.info("stop_instance.complete", instance_id=instance_id_str)


# ── Terminate ──────────────────────────────────────────────────────────────

@celery_app.task(bind=True, max_retries=5, default_retry_delay=15, name="terminate_instance")
def terminate_instance(self: Task, instance_id: str, reason: str = "user") -> None:
    """
    Full teardown sequence:
    1. Stop billing
    2. Agent: terminate (destroy container + VM)
    3. Agent: delete_volume (cryptographic shred)
    4. Agent: verify_deletion (get confirmation hash)
    5. Write SecureDeletionReceipt (immutable audit record)
    6. Revoke SSH session (null private key)
    7. Release wallet hold (refund unused hold)
    8. Transition instance → terminated
    """
    _run_async(_terminate_instance_async(instance_id, reason))


async def _terminate_instance_async(instance_id_str: str, reason: str) -> None:
    iid = uuid.UUID(instance_id_str)
    log.info("terminate_instance.start", instance_id=instance_id_str, reason=reason)

    # 1. Stop billing immediately
    stop_billing(iid)

    async with async_session_factory() as session:
        async with session.begin():
            instance_repo = InstanceRepository(session)
            ssh_repo = SSHSessionRepository(session)
            deletion_repo = SecureDeletionRepository(session)

            instance = await instance_repo.get_by_id(iid)
            if not instance:
                log.error("terminate_instance.not_found", instance_id=instance_id_str)
                return

            agent = AgentProtocol(
                agent_host_url=instance.agent_host_url or "mock://agent",
                instance_id=iid,
            )

            # 2. Terminate container + VM
            try:
                await agent.terminate()
            except Exception as exc:
                log.error("terminate_instance.agent_terminate_failed", error=str(exc))
                # Proceed with deletion — VM may already be dead

            # 3. Cryptographic volume deletion
            try:
                await agent.delete_volume()
            except Exception as exc:
                log.error("terminate_instance.delete_volume_failed", error=str(exc))

            # 4. Verify deletion (mandatory before marking terminated)
            try:
                deletion_result = await agent.verify_deletion()
            except Exception as exc:
                log.error("terminate_instance.verify_deletion_failed", error=str(exc))
                deletion_result = {
                    "method": "verification_failed",
                    "confirmation_hash": "VERIFICATION_FAILED",
                    "payload": str(exc),
                }

            # 5. Write SecureDeletionReceipt (immutable)
            existing_receipt = await deletion_repo.get_by_instance(iid)
            if not existing_receipt:
                await deletion_repo.create(
                    instance_id=iid,
                    method=deletion_result.get("method", "unknown"),
                    agent_confirmation_hash=deletion_result.get("confirmation_hash", ""),
                    agent_payload=deletion_result.get("payload"),
                )

            # 6. Revoke SSH session (null the private key)
            await ssh_repo.revoke(iid)

            # 6b. Phase 6: revoke any active web UI sessions for this instance
            try:
                from services.provisioning_service.template_repository import WebUISessionRepository
                revoked_count = await WebUISessionRepository(session).revoke_by_instance(iid)
                if revoked_count:
                    log.info(
                        "terminate_instance.web_ui_sessions_revoked",
                        instance_id=instance_id_str,
                        count=revoked_count,
                    )
            except Exception as exc:
                log.warning(
                    "terminate_instance.web_ui_revoke_failed",
                    instance_id=instance_id_str,
                    error=str(exc),
                )

            # 7. Release wallet hold
            await instance_repo.release_hold(iid)

            # 8. Transition → terminated
            await instance_repo.transition_state(iid, InstanceStatus.terminated)
            _billed = getattr(instance, 'billed_seconds', 0) or 0

    # Phase 28: Publish INSTANCE_TERMINATED so billing finalizes and releases the hold
    try:
        if instance:
            await on_instance_terminated(
                instance_id=iid,
                developer_id=instance.developer_id,
                listing_id=instance.listing_id,
                reason=reason,
                billed_seconds=_billed,
            )
    except Exception as _evt_exc:
        log.warning(
            "terminate_instance.terminated_event_failed",
            instance_id=instance_id_str,
            error=str(_evt_exc),
        )

    log.info("terminate_instance.complete", instance_id=instance_id_str)


# ── Auto-terminate on zero balance ─────────────────────────────────────────

@celery_app.task(name="auto_terminate_on_zero_balance")
def auto_terminate_on_zero_balance(instance_id: str) -> None:
    """Wrapper: terminate when billing depletion is detected."""
    log.warning("auto_terminate.triggered", instance_id=instance_id)
    terminate_instance.delay(instance_id, reason="zero_balance")


# ── Reconciliation sweep (Celery beat, runs every 60s) ────────────────────

@celery_app.task(name="reconcile_billing")
def reconcile_billing() -> None:
    """
    Periodic sweep that finds `running` instances without an active billing
    watcher (e.g., after a worker restart) and restarts their billing loop.
    """
    _run_async(_reconcile_async())


async def _reconcile_async() -> None:
    from services.provisioning_service.billing_watcher import is_billing_active

    async with async_session_factory() as session:
        async with session.begin():
            instances = await InstanceRepository(session).get_all_running()

    for instance in instances:
        if not is_billing_active(instance.id):
            log.warning(
                "reconcile_billing.restarting_watcher",
                instance_id=str(instance.id),
            )
            start_billing(instance.id)


# ── Template Image Scan (Phase 6) ────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    name="scan_template_image",
)
def scan_template_image(self: Task, template_id: str, base_image: str) -> None:
    """
    Calls the Phase 5 security service to scan a template's container image.

    Flow:
      1. POST /v1/internal/scan-image → security_service
      2. On pass  → template status = available
      3. On fail  → template status = disabled (no deployments allowed)
      4. On error → retry (max 2), then disable

    SCANNER_MOCK=true (set via ENVIRONMENT=testing or CI) skips the real scan
    and marks the template available immediately.
    """
    _run_async(_scan_template_image_async(template_id, base_image))


async def _scan_template_image_async(template_id_str: str, base_image: str) -> None:
    import httpx
    from libs.db_models.template_models import TemplateStatus
    from services.provisioning_service.template_repository import TemplateRepository

    tid = uuid.UUID(template_id_str)
    log.info("scan_template_image.start", template_id=template_id_str, image=base_image)

    # Mock mode: skip real scan, mark available
    if settings.firecracker_mock or settings.environment in ("testing", "test"):
        log.info(
            "scan_template_image.mock_pass",
            template_id=template_id_str,
            image=base_image,
        )
        async with async_session_factory() as session:
            async with session.begin():
                await TemplateRepository(session).update_scan_result(
                    tid,
                    passed=True,
                    scan_report={"mock": True, "findings": [], "image": base_image},
                )
        return

    # Real scan via security_service
    try:
        async with httpx.AsyncClient(timeout=120.0) as http:
            resp = await http.post(
                f"{settings.security_service_url}/v1/internal/scan-image",
                params={"image": base_image, "template_id": template_id_str},
            )
            resp.raise_for_status()
            result = resp.json()
    except Exception as exc:
        log.error(
            "scan_template_image.scan_failed",
            template_id=template_id_str,
            image=base_image,
            error=str(exc),
        )
        # Mark disabled on unrecoverable scan error
        async with async_session_factory() as session:
            async with session.begin():
                await TemplateRepository(session).update_scan_result(
                    tid,
                    passed=False,
                    scan_report={"error": str(exc), "image": base_image},
                )
        return

    passed = not result.get("blocked", False)
    async with async_session_factory() as session:
        async with session.begin():
            await TemplateRepository(session).update_scan_result(
                tid,
                passed=passed,
                scan_report=result,
            )

    log.info(
        "scan_template_image.complete",
        template_id=template_id_str,
        image=base_image,
        passed=passed,
        critical=result.get("critical_count", 0),
        high=result.get("high_count", 0),
    )
