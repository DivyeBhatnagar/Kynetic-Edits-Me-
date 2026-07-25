"""
Services/host_service/verification_service.py
v8 Feature 3 — Verified Hosts Engine.

Implements:
1. Verification application submission (apply_for_verification)
2. Automatic Silver-level verification checks (evaluate_automatic_silver_verification)
3. Gold-level eligibility checks (evaluate_gold_eligibility)
4. Admin verification review queue and decisions (process_admin_review)
5. Admin revocation cascade with reputation penalties (revoke_host_verification)
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.host_models import Host, HostVerification, VerificationDocument
from libs.db_models.user_models import User
from services.reputation_pricing_service.reputation_engine import emit_reputation_event


async def apply_for_verification(
    session: AsyncSession,
    host_id: uuid.UUID,
    level: str = "silver",
    documents: list[dict[str, str]] | None = None,
) -> HostVerification:
    """
    Submit a verification application for a host.
    """
    level_clean = level.lower()
    if level_clean not in ("silver", "gold", "enterprise"):
        raise ValueError(f"Invalid verification level: {level}")

    verification = HostVerification(
        host_id=host_id,
        level=level_clean,
        status="pending",
        submitted_at=datetime.now(UTC),
    )
    session.add(verification)
    await session.flush()

    if documents:
        for doc in documents:
            doc_row = VerificationDocument(
                verification_id=verification.id,
                document_type=doc.get("document_type", "gov_id"),
                storage_url=doc.get("storage_url", "s3://kynetic-docs/placeholder"),
                status="pending",
            )
            session.add(doc_row)
        await session.flush()

    # Automatic evaluation for Silver level
    if level_clean == "silver":
        await evaluate_automatic_silver_verification(session, host_id, verification.id)

    return verification


async def evaluate_automatic_silver_verification(
    session: AsyncSession,
    host_id: uuid.UUID,
    verification_id: uuid.UUID | None = None,
) -> bool:
    """
    Automatic check for Silver verification: requires host user email/account active.
    """
    h_stmt = select(Host, User).join(User, Host.user_id == User.id).where(Host.id == host_id)
    res = await session.execute(h_stmt)
    row = res.first()
    if not row:
        return False

    host, user = row
    if not user.email:
        return False

    # Find pending verification if not passed
    if not verification_id:
        v_stmt = (
            select(HostVerification)
            .where(HostVerification.host_id == host_id, HostVerification.level == "silver")
            .order_by(HostVerification.submitted_at.desc())
            .limit(1)
        )
        v_res = await session.execute(v_stmt)
        verif = v_res.scalars().first()
    else:
        v_stmt = select(HostVerification).where(HostVerification.id == verification_id)
        v_res = await session.execute(v_stmt)
        verif = v_res.scalars().first()

    if verif:
        verif.status = "approved"
        verif.reviewed_at = datetime.now(UTC)

    host.verification_level = "silver"
    await emit_reputation_event(
        session, host_id, "job_completed", impact_delta=0.10, metadata={"reason": "Silver verification approved"}
    )
    return True


async def evaluate_gold_eligibility(
    session: AsyncSession,
    host_id: uuid.UUID,
) -> dict[str, Any]:
    """
    Evaluate eligibility for Gold verification.
    """
    h_stmt = select(Host).where(Host.id == host_id)
    res = await session.execute(h_stmt)
    host = res.scalars().first()
    if not host:
        return {"eligible": False, "reasons": ["Host not found"]}

    reasons = []
    if host.verification_level not in ("silver", "gold", "enterprise"):
        reasons.append("Host must have at least Silver verification")

    # Check reputation
    from libs.db_models.reputation_pricing_models import ReputationScore
    r_stmt = (
        select(ReputationScore)
        .where(ReputationScore.host_id == host_id)
        .order_by(ReputationScore.computed_at.desc())
        .limit(1)
    )
    r_res = await session.execute(r_stmt)
    rep = r_res.scalars().first()
    comp_score = float(rep.composite_score) if rep else 0.50

    if comp_score < 0.70:
        reasons.append(f"Composite reputation score ({comp_score:.2f}) must be >= 0.70")

    eligible = len(reasons) == 0
    return {"eligible": eligible, "reasons": reasons, "composite_score": comp_score}


async def process_admin_review(
    session: AsyncSession,
    verification_id: uuid.UUID,
    admin_id: uuid.UUID,
    decision: str,
    rejection_reason: str | None = None,
) -> HostVerification:
    """
    Admin review action: approve or reject a host verification application.
    """
    decision_clean = decision.lower()
    if decision_clean not in ("approved", "rejected"):
        raise ValueError("Decision must be 'approved' or 'rejected'")

    v_stmt = select(HostVerification).where(HostVerification.id == verification_id)
    res = await session.execute(v_stmt)
    verif = res.scalars().first()
    if not verif:
        raise ValueError(f"Verification {verification_id} not found")

    now = datetime.now(UTC)
    verif.reviewed_by = admin_id
    verif.reviewed_at = now

    if decision_clean == "approved":
        verif.status = "approved"
        # Update host level
        h_stmt = select(Host).where(Host.id == verif.host_id)
        h_res = await session.execute(h_stmt)
        host = h_res.scalars().first()
        if host:
            host.verification_level = verif.level
        await emit_reputation_event(
            session, verif.host_id, "job_completed", impact_delta=0.15, metadata={"level": verif.level, "admin_id": str(admin_id)}
        )
    else:
        verif.status = "rejected"
        verif.rejection_reason = rejection_reason

    return verif


async def revoke_host_verification(
    session: AsyncSession,
    host_id: uuid.UUID,
    admin_id: uuid.UUID,
    reason: str = "Policy violation or trust breakdown",
) -> bool:
    """
    Revoke a host's verification level, resetting to 'unverified' and issuing a reputation penalty.
    """
    h_stmt = select(Host).where(Host.id == host_id)
    res = await session.execute(h_stmt)
    host = res.scalars().first()
    if not host:
        return False

    host.verification_level = "unverified"
    host.trust_state = "flagged"

    # Mark active verifications revoked
    v_stmt = (
        select(HostVerification)
        .where(HostVerification.host_id == host_id, HostVerification.status == "approved")
    )
    v_res = await session.execute(v_stmt)
    verifs = v_res.scalars().all()
    now = datetime.now(UTC)
    for v in verifs:
        v.status = "revoked"
        v.reviewed_by = admin_id
        v.reviewed_at = now
        v.rejection_reason = reason

    # Emit penalty event
    await emit_reputation_event(
        session, host_id, "violation_flagged", impact_delta=-0.35, metadata={"admin_id": str(admin_id), "reason": reason}
    )
    return True


async def get_verification_status(
    session: AsyncSession,
    host_id: uuid.UUID,
) -> dict[str, Any]:
    """
    Fetch verification status and applications for a host.
    """
    h_stmt = select(Host).where(Host.id == host_id)
    h_res = await session.execute(h_stmt)
    host = h_res.scalars().first()
    if not host:
        return {"host_id": str(host_id), "verification_level": "unverified", "applications": []}

    v_stmt = (
        select(HostVerification)
        .where(HostVerification.host_id == host_id)
        .order_by(HostVerification.submitted_at.desc())
    )
    v_res = await session.execute(v_stmt)
    verifs = v_res.scalars().all()

    apps = [
        {
            "id": str(v.id),
            "level": v.level,
            "status": v.status,
            "submitted_at": v.submitted_at.isoformat(),
            "reviewed_at": v.reviewed_at.isoformat() if v.reviewed_at else None,
            "rejection_reason": v.rejection_reason,
        }
        for v in verifs
    ]

    return {
        "host_id": str(host_id),
        "verification_level": host.verification_level,
        "trust_state": host.trust_state,
        "applications": apps,
    }
