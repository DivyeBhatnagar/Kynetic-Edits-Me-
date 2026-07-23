"""
Provisioning Service — Scheduler.

`schedule_instance()` is the single entry point for launching a compute
instance. It enforces the following pre-flight checks before any
infrastructure work begins:

1. Listing exists, is active, and is available
2. Developer has sufficient wallet balance (≥ 1 hour hold)
3. Host is verified and reachable (host_service ping)

On success:
  - Places a wallet hold (debited immediately, refunded on terminate)
  - Creates the Instance record (status=pending)
  - Enqueues the `provision_instance` Celery task
  - Returns the Instance ID immediately (async provisioning)
"""

import uuid
from decimal import Decimal, ROUND_UP

import httpx
import structlog

from libs.db_models.provisioning_models import InstanceStatus
from services.provisioning_service.config import get_settings
from services.provisioning_service.repository import InstanceRepository
from services.provisioning_service.wireguard import allocate_wireguard_ip

log = structlog.get_logger(__name__)
settings = get_settings()


class SchedulerError(Exception):
    """Base class for scheduler validation failures."""
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code  # machine-readable code for API error responses


class InsufficientBalanceError(SchedulerError):
    def __init__(self, required: Decimal, available: Decimal):
        super().__init__(
            f"Insufficient balance: need ${required:.6f}, have ${available:.6f}",
            code="insufficient_balance",
        )
        self.required = required
        self.available = available


class ListingUnavailableError(SchedulerError):
    def __init__(self, listing_id: uuid.UUID):
        super().__init__(f"Listing {listing_id} is not available", code="listing_unavailable")


class HostUnreachableError(SchedulerError):
    def __init__(self, host_id: uuid.UUID):
        super().__init__(f"Host {host_id} is not reachable", code="host_unreachable")


async def _fetch_listing(listing_id: uuid.UUID) -> dict:
    """Fetch listing details from marketplace_service."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{settings.marketplace_service_url}/listings/{listing_id}"
        )
        if resp.status_code == 404:
            raise ListingUnavailableError(listing_id)
        resp.raise_for_status()
        return resp.json()


async def _fetch_wallet_balance(developer_id: uuid.UUID, token: str) -> dict:
    """Fetch wallet balance from wallet_billing_service."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{settings.wallet_billing_service_url}/wallet/balance",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        return resp.json()


async def _place_hold(
    developer_id: uuid.UUID, amount_usd: Decimal, token: str
) -> str:
    """
    Debit the hold amount from the wallet.
    Returns transaction_id for the hold record.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{settings.wallet_billing_service_url}/wallet/hold",
            json={
                "amount_usd": str(amount_usd),
                "description": "Instance launch hold (1 hour)",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        return resp.json()["transaction_id"]


async def _fetch_host(host_id: uuid.UUID) -> dict:
    """Fetch host details from host_service to get agent URL."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{settings.host_service_url}/hosts/{host_id}"
        )
        if resp.status_code == 404:
            raise HostUnreachableError(host_id)
        resp.raise_for_status()
        return resp.json()


async def schedule_instance(
    *,
    listing_id: uuid.UUID,
    developer_id: uuid.UUID,
    auth_token: str,
    instance_repo: InstanceRepository,
    template_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """
    Pre-flight checks → wallet hold → create Instance → enqueue Celery task.

    Returns the new instance_id. Provisioning happens asynchronously.
    The caller should poll GET /instances/{id} for status updates.

    Raises SchedulerError subclasses on validation failures.
    """
    # ── 1. Fetch + validate listing ────────────────────────────────────────
    log.info("scheduler.fetching_listing", listing_id=str(listing_id))
    listing = await _fetch_listing(listing_id)

    if listing.get("status") != "active":
        raise ListingUnavailableError(listing_id)
    if not listing.get("is_available", False):
        raise ListingUnavailableError(listing_id)

    price_per_second_usd = Decimal(str(listing["price_per_second_usd"]))
    host_id = uuid.UUID(listing["host_id"])

    # ── 1b. Fetch + validate template hardware requirements ──────────────────
    if template_id:
        from services.provisioning_service.template_repository import TemplateRepository
        template_repo = TemplateRepository(instance_repo._session)
        template = await template_repo.get_by_id(template_id)
        if not template:
            raise SchedulerError(f"Template {template_id} not found", code="template_not_found")
        
        # Check listing hardware specs against template requirements
        listing_vram = listing.get("gpu_vram_gb")
        listing_ram = listing.get("ram_gb")
        
        if template.required_gpu_vram_gb:
            if not listing_vram or float(listing_vram) < float(template.required_gpu_vram_gb):
                raise SchedulerError(
                    f"Listing has insufficient VRAM: need {template.required_gpu_vram_gb} GB, has {listing_vram or 0} GB",
                    code="insufficient_hardware",
                )
        
        if template.required_ram_gb:
            if not listing_ram or float(listing_ram) < float(template.required_ram_gb):
                raise SchedulerError(
                    f"Listing has insufficient RAM: need {template.required_ram_gb} GB, has {listing_ram or 0} GB",
                    code="insufficient_hardware",
                )

    # ── 2. Calculate hold amount (1 hour of compute) ───────────────────────
    hold_seconds = int(settings.hold_hours * 3600)
    hold_amount = (price_per_second_usd * hold_seconds).quantize(
        Decimal("0.000001"), rounding=ROUND_UP
    )

    # ── 3. Check wallet balance ────────────────────────────────────────────
    log.info("scheduler.checking_balance", developer_id=str(developer_id))
    wallet = await _fetch_wallet_balance(developer_id, auth_token)
    balance_usd = Decimal(str(wallet["balance_usd"]))

    if balance_usd < hold_amount:
        raise InsufficientBalanceError(required=hold_amount, available=balance_usd)

    # ── 4. Fetch host info (agent URL, public IP) ──────────────────────────
    log.info("scheduler.fetching_host", host_id=str(host_id))
    host = await _fetch_host(host_id)
    agent_host_url = host.get("agent_url", f"https://{host.get('ip_address')}:8443")
    public_ip = host.get("public_ip")

    # ── 5. Place wallet hold ───────────────────────────────────────────────
    log.info("scheduler.placing_hold", amount=str(hold_amount))
    await _place_hold(developer_id, hold_amount, auth_token)

    # ── 6. Create Instance record ──────────────────────────────────────────
    instance = await instance_repo.create(
        developer_id=developer_id,
        listing_id=listing_id,
        host_id=host_id,
        hold_amount=hold_amount,
        price_per_second_usd=price_per_second_usd,
        agent_host_url=agent_host_url,
        public_ip=public_ip,
        template_id=template_id,
    )

    # ── 7. Enqueue Celery provisioning task ────────────────────────────────
    # Import here to avoid circular imports at module load time
    from services.provisioning_service.tasks import provision_instance
    provision_instance.delay(str(instance.id))

    log.info(
        "scheduler.instance_queued",
        instance_id=str(instance.id),
        listing_id=str(listing_id),
        host_id=str(host_id),
    )
    return instance.id
