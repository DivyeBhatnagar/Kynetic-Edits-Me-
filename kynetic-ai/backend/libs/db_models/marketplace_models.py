"""
Marketplace DB Models.

Tables:
  listings           — resource-agnostic compute listings
  stripe_accounts    — Stripe customer / Connect IDs per user

Enums:
  ResourceType    — gpu | cpu | ram | nvme | workstation_bundle
  ListingStatus   — draft | active | paused | delisted
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from libs.db_models.database import Base


# ── Enums ──────────────────────────────────────────────────────────────────

import enum


class ResourceType(str, enum.Enum):
    gpu = "gpu"
    cpu = "cpu"
    ram = "ram"
    nvme = "nvme"
    workstation_bundle = "workstation_bundle"


class ListingStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    paused = "paused"
    delisted = "delisted"





# ── Models ─────────────────────────────────────────────────────────────────

class Listing(Base):
    """
    A compute listing offered by a verified host.

    Resource-agnostic: can represent a GPU slot, CPU cluster,
    RAM allocation, NVMe volume, or a full workstation bundle.
    Hardware specs and benchmark scores are snapshotted at listing
    creation from the host's latest verified data.
    """

    __tablename__ = "listings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    host_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hosts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Resource type — determines which fields are relevant
    resource_type: Mapped[ResourceType] = mapped_column(
        Enum(ResourceType, name="resource_type_enum", create_type=True),
        nullable=False,
        index=True,
    )

    # Hardware attributes (nullable — only filled for relevant resource types)
    gpu_model: Mapped[str | None] = mapped_column(String(200))
    gpu_count: Mapped[int | None] = mapped_column(Integer)
    gpu_vram_gb: Mapped[float | None] = mapped_column(Numeric(10, 2))
    cpu_cores: Mapped[int | None] = mapped_column(Integer)
    ram_gb: Mapped[float | None] = mapped_column(Numeric(10, 2))
    storage_gb: Mapped[float | None] = mapped_column(Numeric(10, 2))
    storage_type: Mapped[str | None] = mapped_column(String(20))  # nvme | ssd | hdd

    # Pricing — stored in both currencies; no float, use Numeric(12, 6)
    price_per_hour_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), nullable=False
    )
    price_per_hour_inr: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), nullable=False
    )
    price_per_second_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 10), nullable=False
    )
    price_per_second_inr: Mapped[Decimal] = mapped_column(
        Numeric(18, 10), nullable=False
    )

    # Location
    region: Mapped[str | None] = mapped_column(String(100), index=True)

    # Snapshotted benchmark scores from Phase 2 at time of listing creation
    benchmark_scores: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    status: Mapped[ListingStatus] = mapped_column(
        Enum(ListingStatus, name="listing_status_enum", create_type=True),
        nullable=False,
        default=ListingStatus.draft,
        index=True,
    )

    # Title / description (optional freeform)
    title: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("price_per_hour_usd >= 0", name="listing_price_usd_positive"),
        CheckConstraint("price_per_hour_inr >= 0", name="listing_price_inr_positive"),
        Index("ix_listings_status_resource_type", "status", "resource_type"),
        Index("ix_listings_region_status", "region", "status"),
        Index("ix_listings_gpu_model", "gpu_model"),
    )





class StripeAccount(Base):
    """
    Maps a Kynetic user to their Stripe customer and/or Connect account IDs.

    - Developers: have `stripe_customer_id` (for payment processing)
    - Hosts: additionally have `stripe_connect_account_id` (for payouts via Connect)
    """

    __tablename__ = "stripe_accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    stripe_customer_id: Mapped[str | None] = mapped_column(String(200), index=True)
    stripe_connect_account_id: Mapped[str | None] = mapped_column(String(200), index=True)

    # Onboarding completion state for Connect (hosts need to complete Stripe onboarding)
    connect_onboarding_complete: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_stripe_accounts_user_id"),
    )
