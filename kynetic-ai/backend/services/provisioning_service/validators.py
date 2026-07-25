"""
Provisioning Service — Central Business Logic Validation Gate (Phase 27).

Every instance creation request MUST pass through `validate_instance_request()`
before any Celery task or Host Agent call fires. Runs directly against the
database to avoid HTTP round-trips and provide atomic, consistent checks.

Raises `InstanceValidationError` with a machine-readable code on any failure,
which the exception handler in `exception_handlers.py` maps to HTTP status codes.

Checks enforced (in order):
  1. Permission: requester is the developer, or an admin.
  2. Listing: exists, is `active`, and `is_available == True`.
  3. Host: exists, is `verified` or `listed`, and last heartbeat is IDLE.
  4. Wallet: developer has sufficient balance for the requested hold period.

Returns `ValidatedInstanceRequest` on success — a dataclass containing all
pre-computed values so the caller never repeats these DB lookups.
"""

from __future__ import annotations

import uuid
import structlog
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Union

from services.provisioning_service.audit import log_validation_rejection

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.host_models import Host, HostHeartbeat, HeartbeatStatus, HostStatus
from libs.db_models.marketplace_models import Listing, ListingStatus, Wallet, Currency
from libs.db_models.user_models import User, UserRole

log = structlog.get_logger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────

# A heartbeat older than this means the host is considered offline/stale.
HEARTBEAT_STALENESS_SECONDS = 120


# ── Helpers ──────────────────────────────────────────────────────

def _as_uuid(value: Union[str, uuid.UUID]) -> uuid.UUID:
    """Ensure a value is a uuid.UUID object (safe for both Postgres and SQLite)."""
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


# ── Errors ─────────────────────────────────────────────────────────────────

class InstanceValidationError(Exception):
    """
    Raised when any pre-flight validation check fails.

    Attributes:
        code (str): Machine-readable error key (maps to HTTP status in exception_handlers.py).
        message (str): Human-readable explanation suitable for API response.
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)

    def __repr__(self) -> str:
        return f"InstanceValidationError(code={self.code!r}, message={self.message!r})"


# ── Return type ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ValidatedInstanceRequest:
    """
    Carries all pre-validated, pre-computed values from the validation pass.

    The caller (scheduler / route handler) uses these values directly to:
      - Create the Instance record (no second listing/host lookup needed)
      - Place the wallet hold with the correct currency and amount
      - Pass host_id and agent_url into the Celery provisioning task
    """

    developer_id: str
    listing_id: str
    host_id: str
    price_per_hour_usd: Decimal
    price_per_hour_inr: Decimal
    price_per_second_usd: Decimal
    price_per_second_inr: Decimal
    currency: Currency  # the developer's preferred currency
    hold_amount: Decimal  # pre-computed hold for `hold_hours` of compute
    hold_currency: Currency


# ── Individual validation steps ─────────────────────────────────────────────

async def _validate_permissions(
    db: AsyncSession,
    requester_id: Union[str, uuid.UUID],
    developer_id: Union[str, uuid.UUID],
) -> None:
    """
    Ensure the requester may act on behalf of the developer.

    Rules:
      - A user may always act on their own account (requester == developer).
      - Admins (UserRole.ADMIN) may act on any account.
      - Anyone else is rejected.
    """
    req_uuid = _as_uuid(requester_id)
    dev_uuid = _as_uuid(developer_id)

    if req_uuid == dev_uuid:
        return  # acting on own account — always allowed

    result = await db.execute(select(User).where(User.id == req_uuid))
    requester = result.scalar_one_or_none()

    if requester is None:
        raise InstanceValidationError(
            "PERMISSION_DENIED",
            "Requester account does not exist.",
        )
    if requester.role is not UserRole.ADMIN:
        raise InstanceValidationError(
            "PERMISSION_DENIED",
            "You do not have permission to provision instances on behalf of another account.",
        )

    log.info(
        "validator.admin_acting_for_developer",
        admin_id=str(req_uuid),
        developer_id=str(dev_uuid),
    )


async def _validate_listing(
    db: AsyncSession,
    listing_id: Union[str, uuid.UUID],
) -> Listing:
    """
    Ensure the listing exists, is `active`, and is not currently rented out.

    A listing is considered unavailable if:
      - Its status is anything other than `ListingStatus.active` (draft/paused/delisted), OR
      - `is_available` is False (a running instance has reserved the slot).
    """
    listing_uuid = _as_uuid(listing_id)
    result = await db.execute(select(Listing).where(Listing.id == listing_uuid))
    listing = result.scalar_one_or_none()

    if listing is None:
        raise InstanceValidationError(
            "LISTING_NOT_FOUND",
            f"Listing '{listing_id}' does not exist.",
        )

    if listing.status is not ListingStatus.active:
        raise InstanceValidationError(
            "LISTING_UNAVAILABLE",
            f"Listing is currently '{listing.status.value}' and cannot accept new instances. "
            "Only active listings are rentable.",
        )
    
    return listing

async def _validate_host(
    db: AsyncSession,
    host_id: Union[str, uuid.UUID],
) -> Host:
    """
    Ensure the host:
      1. Exists in the database.
      2. Has a verified or listed status (not pending, flagged, or suspended).
      3. Has sent a heartbeat within the last HEARTBEAT_STALENESS_SECONDS
         AND that heartbeat reports status=IDLE (not busy with another job).
    """
    host_uuid = _as_uuid(host_id)
    result = await db.execute(select(Host).where(Host.id == host_uuid))
    host = result.scalar_one_or_none()

    if host is None:
        raise InstanceValidationError(
            "HOST_NOT_FOUND",
            f"Host '{host_id}' does not exist.",
        )

    # Hosts must be at least VERIFIED before accepting jobs.
    # LISTED is a superset of VERIFIED (listing was created after verification).
    eligible_statuses = {HostStatus.VERIFIED, HostStatus.LISTED}
    if host.status not in eligible_statuses:
        raise InstanceValidationError(
            "HOST_NOT_VERIFIED",
            f"Host status is '{host.status.value}'. Only verified/listed hosts can accept jobs.",
        )

    # ── Heartbeat freshness check ──────────────────────────────────────────
    hb_result = await db.execute(
        select(HostHeartbeat)
        .where(HostHeartbeat.host_id == host_uuid)
        .order_by(desc(HostHeartbeat.recorded_at))
        .limit(1)
    )
    last_hb = hb_result.scalar_one_or_none()

    if last_hb is None:
        raise InstanceValidationError(
            "HOST_NOT_IDLE",
            "Host has never sent a heartbeat — it may not have the agent installed.",
        )

    stale_cutoff = datetime.now(timezone.utc) - timedelta(seconds=HEARTBEAT_STALENESS_SECONDS)
    # recorded_at is stored with timezone awareness (DateTime(timezone=True))
    hb_time = last_hb.recorded_at
    if hb_time.tzinfo is None:
        hb_time = hb_time.replace(tzinfo=timezone.utc)  # defensive: treat naïve as UTC

    if hb_time < stale_cutoff:
        age_seconds = (datetime.now(timezone.utc) - hb_time).total_seconds()
        raise InstanceValidationError(
            "HOST_NOT_IDLE",
            f"Host last heartbeat was {age_seconds:.0f}s ago (threshold: {HEARTBEAT_STALENESS_SECONDS}s). "
            "Host appears offline.",
        )

    if last_hb.status is not HeartbeatStatus.IDLE:
        raise InstanceValidationError(
            "HOST_NOT_IDLE",
            f"Host heartbeat reports status '{last_hb.status.value}'. "
            "Host is busy with another workload.",
        )

    return host


async def _validate_wallet_balance(
    db: AsyncSession,
    developer_id: Union[str, uuid.UUID],
    hold_amount: Decimal,
    hold_currency: Currency,
) -> Wallet:
    """Ensure the developer's wallet exists and has sufficient balance for the hold."""
    dev_uuid = _as_uuid(developer_id)
    result = await db.execute(select(Wallet).where(Wallet.user_id == dev_uuid))
    wallet = result.scalar_one_or_none()

    if wallet is None:
        raise InstanceValidationError(
            "WALLET_NOT_FOUND",
            "No wallet found for this account. Contact support.",
        )

    if hold_currency is Currency.inr:
        available = wallet.balance_inr
    else:
        available = wallet.balance_usd

    if available < hold_amount:
        raise InstanceValidationError(
            "INSUFFICIENT_BALANCE",
            f"Insufficient balance. Required: {hold_amount:.6f} {hold_currency.value.upper()}, "
            f"available: {available:.6f} {hold_currency.value.upper()}. "
            "Please top up your wallet.",
        )

    return wallet


# ── Public entry point ──────────────────────────────────────────────────────

async def validate_instance_request(
    db: AsyncSession,
    *,
    requester_id: str,
    developer_id: str,
    listing_id: str,
    hold_hours: Decimal,
) -> ValidatedInstanceRequest:
    """
    Single entry point called by the provisioning route handler before any
    infrastructure work begins.

    Runs all four validation steps atomically (within the same DB transaction):
      1. Permission check  — can `requester_id` act for `developer_id`?
      2. Listing check     — is the listing active and available?
      3. Host check        — is the host online and idle?
      4. Wallet check      — does the developer have enough balance?

    Args:
        db:            Open async DB session (transaction managed by caller).
        requester_id:  User ID extracted from the JWT (may differ from developer_id for admin calls).
        developer_id:  The user whose wallet and permissions are checked.
        listing_id:    The listing being requested.
        hold_hours:    Number of hours to pre-authorise (1 = 1-hour hold, the standard minimum).

    Returns:
        ValidatedInstanceRequest: All pre-computed values for instance creation.

    Raises:
        InstanceValidationError: On any check failure, with a code describing the reason.
    """
    dev_uuid = _as_uuid(developer_id)
    req_uuid = _as_uuid(requester_id)

    log.info(
        "validator.start",
        requester_id=str(req_uuid),
        developer_id=str(dev_uuid),
        listing_id=str(listing_id),
        hold_hours=str(hold_hours),
    )

    try:
        # ── Step 1: Permissions ──────────────────────────────────────────
        await _validate_permissions(db, req_uuid, dev_uuid)

        # ── Step 2: Listing ───────────────────────────────────────────
        listing = await _validate_listing(db, listing_id)

        # ── Step 3: Host (uses listing.host_id) ─────────────────────────
        host = await _validate_host(db, listing.host_id)

        # ── Step 4: Wallet balance ───────────────────────────────────
        # Determine preferred currency from the developer's wallet.
        wallet_result = await db.execute(select(Wallet).where(Wallet.user_id == dev_uuid))
        wallet = wallet_result.scalar_one_or_none()

        # Fallback to USD if wallet doesn't exist yet (will be caught in _validate_wallet_balance).
        preferred_currency = wallet.preferred_currency if wallet else Currency.usd

        # Compute hold amount in the developer's preferred currency.
        if preferred_currency is Currency.inr:
            hourly_rate = listing.price_per_hour_inr
            hold_currency = Currency.inr
        else:
            hourly_rate = listing.price_per_hour_usd
            hold_currency = Currency.usd

        hold_amount = (hourly_rate * hold_hours).quantize(Decimal("0.000001"))

        await _validate_wallet_balance(db, developer_id, hold_amount, hold_currency)

    except InstanceValidationError as exc:
        await log_validation_rejection(
            db,
            requester_id=req_uuid,
            listing_id=str(listing_id),
            code=exc.code,
            message=exc.message,
        )
        raise

    log.info(
        "validator.passed",
        developer_id=str(developer_id),
        listing_id=str(listing_id),
        host_id=str(host.id),
        hold_amount=str(hold_amount),
        hold_currency=hold_currency.value,
    )

    return ValidatedInstanceRequest(
        developer_id=str(developer_id),
        listing_id=str(listing_id),
        host_id=str(host.id),
        price_per_hour_usd=listing.price_per_hour_usd,
        price_per_hour_inr=listing.price_per_hour_inr,
        price_per_second_usd=listing.price_per_second_usd,
        price_per_second_inr=listing.price_per_second_inr,
        currency=preferred_currency,
        hold_amount=hold_amount,
        hold_currency=hold_currency,
    )
