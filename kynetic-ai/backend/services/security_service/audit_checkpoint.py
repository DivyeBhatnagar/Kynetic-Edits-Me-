"""
Security Service — Audit Log Hash Chain Checkpoint & Verification Engine (Part 20).

Periodically computes and exports the current SHA-256 audit log chain tip to external
immutable storage, and verifies full historical chain integrity from genesis root to head.
"""

import hashlib
import json

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.user_models import AuditLog

log = structlog.get_logger(__name__)

GENESIS_HASH = "GENESIS_HASH_CHAIN_ROOT_0000000000000000000000000000000000000000"


class AuditChainTamperError(Exception):
    """Raised when an audit log hash chain mismatch is detected during verification."""
    pass


async def generate_chain_tip_checkpoint(session: AsyncSession) -> dict:
    """
    Fetches the latest audit log entry and computes the immutable chain tip checkpoint payload.
    """
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(1)
    res = await session.execute(stmt)
    latest_entry = res.scalar_one_or_none()

    if not latest_entry:
        return {
            "checkpoint_status": "empty",
            "chain_tip_hash": GENESIS_HASH,
            "total_entries": 0,
        }

    checkpoint_payload = {
        "checkpoint_status": "active",
        "latest_log_id": str(latest_entry.id),
        "chain_tip_hash": latest_entry.entry_hash,
        "prev_hash": latest_entry.prev_hash,
        "action": latest_entry.action,
        "created_at": latest_entry.created_at.isoformat() if latest_entry.created_at else None,
    }

    log.info(
        "audit_checkpoint.tip_generated",
        tip_hash=latest_entry.entry_hash,
        log_id=str(latest_entry.id),
    )
    return checkpoint_payload


async def verify_audit_chain_integrity(session: AsyncSession) -> bool:
    """
    Recomputes the entire audit log SHA-256 hash chain from genesis root to current head.
    Raises AuditChainTamperError if any row has been retroactively modified or deleted.
    """
    stmt = select(AuditLog).order_by(AuditLog.created_at.asc())
    res = await session.execute(stmt)
    entries = res.scalars().all()

    if not entries:
        log.info("audit_checkpoint.verify_empty_chain")
        return True

    expected_prev = GENESIS_HASH
    for idx, entry in enumerate(entries):
        if entry.prev_hash != expected_prev:
            log.critical(
                "audit_checkpoint.tamper_detected",
                row_index=idx,
                log_id=str(entry.id),
                expected_prev=expected_prev,
                actual_prev=entry.prev_hash,
            )
            raise AuditChainTamperError(
                f"Audit chain broken at row index {idx} (ID: {entry.id}): "
                f"expected prev_hash {expected_prev}, got {entry.prev_hash}"
            )

        now_str = entry.created_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ") if entry.created_at else ""
        payload = f"{entry.prev_hash}|{now_str}|{entry.actor_id}|{entry.action}|{entry.resource_type}|{entry.resource_id}"
        recalculated_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()

        if entry.entry_hash != recalculated_hash:
            log.critical(
                "audit_checkpoint.row_tamper_detected",
                row_index=idx,
                log_id=str(entry.id),
                stored_hash=entry.entry_hash,
                recalculated_hash=recalculated_hash,
            )
            raise AuditChainTamperError(
                f"Audit log entry content tampered at row {idx} (ID: {entry.id})"
            )

        expected_prev = entry.entry_hash

    log.info("audit_checkpoint.integrity_verified", total_rows=len(entries))
    return True
