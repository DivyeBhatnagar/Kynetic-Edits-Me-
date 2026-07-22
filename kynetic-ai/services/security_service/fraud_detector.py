"""
Security Service — Wallet Fraud Detector.

Rule-based fraud detection scanning recent wallet_transactions.

Rules implemented (MVP tier):
  1. Rapid top-up burst: > N top-ups in M minutes → flag
  2. Rapid top-up + full spend: fund → near-zero balance in < 1 hour → flag
  3. Chargeback history: any prior chargeback → flag future top-ups

Each rule can independently flag a user. Flagged users have a
SecurityEventLog entry written and optionally trigger wallet freeze.

In mock mode: all scans return clean results.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import structlog

from services.security_service.config import get_settings
from services.security_service.schemas import FraudScanResult

log = structlog.get_logger(__name__)
settings = get_settings()


async def scan_user_for_fraud(
    user_id: uuid.UUID,
    auth_token: str = "INTERNAL",
) -> FraudScanResult:
    """
    Fetches the user's recent wallet transactions and runs all fraud rules.
    Returns a FraudScanResult — the caller decides what action to take.

    In mock mode: returns a clean result immediately.
    """
    if settings.scanner_mock:
        return FraudScanResult(
            user_id=user_id,
            flagged=False,
            rules_triggered=[],
            details={"mock": True},
        )

    # Fetch recent transactions from wallet_billing_service
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.wallet_billing_service_url}/wallet/transactions?page_size=50",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        log.error("fraud_detector.fetch_failed", user_id=str(user_id), error=str(exc))
        return FraudScanResult(
            user_id=user_id,
            flagged=False,
            rules_triggered=[],
            details={"error": str(exc)},
        )

    transactions = data.get("items", [])
    rules_triggered: list[str] = []
    details: dict[str, Any] = {}

    now = datetime.now(tz=timezone.utc)
    window_start = now - timedelta(minutes=settings.fraud_topup_window_minutes)

    # ── Rule 1: Rapid top-up burst ────────────────────────────────────────
    recent_topups = [
        t for t in transactions
        if t.get("transaction_type") == "topup"
        and datetime.fromisoformat(t["created_at"]).replace(tzinfo=timezone.utc) > window_start
    ]
    if len(recent_topups) >= settings.fraud_topup_count_threshold:
        rules_triggered.append("rapid_topup_burst")
        details["rapid_topup_count"] = len(recent_topups)
        details["rapid_topup_window_minutes"] = settings.fraud_topup_window_minutes
        log.warning(
            "fraud_detector.rapid_topup",
            user_id=str(user_id),
            count=len(recent_topups),
        )

    # ── Rule 2: Rapid spend after top-up ─────────────────────────────────
    # Look for a top-up followed by near-full spend within 1 hour
    for topup in recent_topups:
        topup_time = datetime.fromisoformat(topup["created_at"]).replace(tzinfo=timezone.utc)
        topup_amount = float(topup.get("amount", 0))
        hour_after = topup_time + timedelta(hours=1)
        debits_after = [
            t for t in transactions
            if t.get("transaction_type") == "debit"
            and topup_time < datetime.fromisoformat(t["created_at"]).replace(tzinfo=timezone.utc) < hour_after
        ]
        total_spent = sum(float(t.get("amount", 0)) for t in debits_after)
        if total_spent > topup_amount * 0.9:
            rules_triggered.append("rapid_spend_after_topup")
            details["rapid_spend_topup_amount"] = topup_amount
            details["rapid_spend_total"] = total_spent
            break

    # ── Rule 3: Chargeback history ────────────────────────────────────────
    chargebacks = [t for t in transactions if t.get("transaction_type") == "chargeback"]
    if chargebacks:
        rules_triggered.append("chargeback_history")
        details["chargeback_count"] = len(chargebacks)

    flagged = len(rules_triggered) > 0
    if flagged:
        log.warning(
            "fraud_detector.flagged",
            user_id=str(user_id),
            rules=rules_triggered,
        )

    return FraudScanResult(
        user_id=user_id,
        flagged=flagged,
        rules_triggered=rules_triggered,
        details=details,
    )
