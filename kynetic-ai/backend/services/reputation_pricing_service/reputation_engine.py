"""
Services/reputation_pricing_service/reputation_engine.py
v8 Feature 2 — Host Reputation System Engine.

Implements:
1. Append-only event emission (emit_reputation_event)
2. Exponential time-decay score calculation (compute_decayed_reputation)
3. Trust state evaluation & transition (evaluate_trust_state)
4. Audit-logged manual penalty and restore overrides
"""

import json
import math
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.host_models import Host
from libs.db_models.reputation_pricing_models import ReputationEvent, ReputationScore


# Standard event deltas
EVENT_DELTAS: dict[str, Decimal] = {
    "job_completed": Decimal("0.0500"),
    "job_cancelled": Decimal("-0.0200"),  # anti-gaming penalty
    "job_failed": Decimal("-0.1000"),
    "dispute_opened": Decimal("-0.2000"),
    "refund_issued": Decimal("-0.1500"),
    "violation_flagged": Decimal("-0.3500"),
    "manual_penalty": Decimal("-0.2500"),
    "manual_restore": Decimal("0.2500"),
}


async def emit_reputation_event(
    session: AsyncSession,
    host_id: uuid.UUID,
    event_type: str,
    impact_delta: float | Decimal | None = None,
    metadata: dict[str, Any] | None = None,
) -> ReputationEvent:
    """
    Record an append-only event into reputation_events and trigger immediate trust checks.
    """
    if impact_delta is None:
        delta = EVENT_DELTAS.get(event_type, Decimal("0.0000"))
    else:
        delta = Decimal(str(impact_delta))

    event = ReputationEvent(
        host_id=host_id,
        event_type=event_type,
        impact_delta=delta,
        metadata_json=json.dumps(metadata) if metadata else None,
        created_at=datetime.now(UTC),
    )
    session.add(event)
    await session.flush()

    # Immediate penalty check for severe events
    if event_type in ("violation_flagged", "dispute_opened") or delta < Decimal("-0.3000"):
        stmt = (
            update(Host)
            .where(Host.id == host_id)
            .values(trust_state="flagged")
        )
        await session.execute(stmt)

    return event


async def compute_decayed_reputation(
    session: AsyncSession,
    host_id: uuid.UUID,
    half_life_days: float = 30.0,
) -> dict[str, Any]:
    """
    Recompute composite score from append-only events using exponential time decay.
    Formula: score = clamp(0.50 + sum(delta_i * e^(-lambda * (t_now - t_i))), 0.0, 1.0)
    """
    now = datetime.now(UTC)
    lambda_decay = math.log(2.0) / max(half_life_days, 1.0)

    stmt = (
        select(ReputationEvent)
        .where(ReputationEvent.host_id == host_id)
        .order_by(ReputationEvent.created_at.asc())
    )
    res = await session.execute(stmt)
    events = res.scalars().all()

    base_score = 0.50  # Starting baseline
    decayed_delta_sum = 0.0

    completed_jobs = 0
    cancelled_jobs = 0
    failed_jobs = 0
    dispute_count = 0
    refund_count = 0
    violation_count = 0

    for ev in events:
        etype = ev.event_type
        if etype == "job_completed":
            completed_jobs += 1
        elif etype == "job_cancelled":
            cancelled_jobs += 1
        elif etype == "job_failed":
            failed_jobs += 1
        elif etype == "dispute_opened":
            dispute_count += 1
        elif etype == "refund_issued":
            refund_count += 1
        elif etype == "violation_flagged":
            violation_count += 1

        created_at = ev.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)

        dt_days = (now - created_at).total_seconds() / 86400.0
        weight = math.exp(-lambda_decay * max(dt_days, 0.0))
        decayed_delta_sum += float(ev.impact_delta) * weight

    raw_composite = base_score + decayed_delta_sum
    composite_score = round(max(0.0, min(1.0, raw_composite)), 4)

    # Component ratios
    total_jobs = completed_jobs + cancelled_jobs + failed_jobs
    job_success_rate = (completed_jobs / total_jobs) if total_jobs > 0 else None

    # Write ReputationScore snapshot
    snapshot = ReputationScore(
        host_id=host_id,
        composite_score=Decimal(str(composite_score)),
        job_success_rate=Decimal(str(round(job_success_rate, 3))) if job_success_rate is not None else None,
        jobs_evaluated=total_jobs,
        completed_jobs=completed_jobs,
        cancelled_jobs=cancelled_jobs,
        failed_jobs=failed_jobs,
        dispute_count=dispute_count,
        refund_count=refund_count,
        policy_violation_count=violation_count,
        decay_factor=Decimal(str(round(math.exp(-lambda_decay), 4))),
        last_decayed_at=now,
        computed_at=now,
    )
    session.add(snapshot)

    # Evaluate trust state transition
    h_stmt = select(Host).where(Host.id == host_id)
    h_res = await session.execute(h_stmt)
    host = h_res.scalars().first()

    if host:
        new_trust = host.trust_state
        if violation_count > 0 or dispute_count >= 3 or composite_score < 0.25:
            new_trust = "flagged"
        elif composite_score >= 0.80 and total_jobs >= 10:
            new_trust = "established"
        elif total_jobs >= 1:
            new_trust = "building_trust"

        if new_trust != host.trust_state:
            host.trust_state = new_trust

    return {
        "host_id": str(host_id),
        "composite_score": composite_score,
        "job_success_rate": job_success_rate,
        "completed_jobs": completed_jobs,
        "cancelled_jobs": cancelled_jobs,
        "failed_jobs": failed_jobs,
        "dispute_count": dispute_count,
        "refund_count": refund_count,
        "policy_violation_count": violation_count,
        "computed_at": now.isoformat(),
    }


async def get_host_reputation_history(
    session: AsyncSession,
    host_id: uuid.UUID,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """
    Fetch history log of reputation events for a host.
    """
    stmt = (
        select(ReputationEvent)
        .where(ReputationEvent.host_id == host_id)
        .order_by(ReputationEvent.created_at.desc())
        .limit(limit)
    )
    res = await session.execute(stmt)
    events = res.scalars().all()

    return [
        {
            "id": str(ev.id),
            "host_id": str(ev.host_id),
            "event_type": ev.event_type,
            "impact_delta": float(ev.impact_delta),
            "metadata": json.loads(ev.metadata_json) if ev.metadata_json else None,
            "created_at": ev.created_at.isoformat(),
        }
        for ev in events
    ]


async def apply_manual_penalty(
    session: AsyncSession,
    host_id: uuid.UUID,
    admin_id: uuid.UUID,
    impact_delta: float = -0.25,
    reason: str = "Admin manual penalty",
) -> ReputationEvent:
    """
    Admin action to issue a manual reputation penalty.
    """
    meta = {"admin_id": str(admin_id), "reason": reason}
    return await emit_reputation_event(
        session, host_id, "manual_penalty", impact_delta, meta
    )


async def apply_manual_restore(
    session: AsyncSession,
    host_id: uuid.UUID,
    admin_id: uuid.UUID,
    impact_delta: float = 0.25,
    reason: str = "Admin manual restore",
) -> ReputationEvent:
    """
    Admin action to restore host reputation.
    """
    meta = {"admin_id": str(admin_id), "reason": reason}
    return await emit_reputation_event(
        session, host_id, "manual_restore", impact_delta, meta
    )
