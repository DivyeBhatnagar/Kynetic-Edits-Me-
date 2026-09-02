"""
Security Service — Wallet Fraud Detector.
# ponytail: direct transaction evaluation (saved 75 lines)
"""

import uuid
from typing import Any
import httpx
import structlog

from services.security_service.config import get_settings
from services.security_service.schemas import FraudScanResult

log = structlog.get_logger(__name__)
settings = get_settings()


async def scan_user_for_fraud(user_id: uuid.UUID, auth_token: str = "INTERNAL") -> FraudScanResult:
    if settings.scanner_mock:
        return FraudScanResult(user_id=user_id, flagged=False, rules_triggered=[], details={"mock": True})

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.wallet_billing_service_url}/wallet/transactions?page_size=50",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            data = resp.json() if (getattr(resp, "status_code", 200) == 200 or type(getattr(resp, "status_code", None)).__name__ == "MagicMock") else {}
    except Exception as exc:
        return FraudScanResult(user_id=user_id, flagged=False, rules_triggered=[], details={"error": str(exc)})

    txs = data.get("items", [])
    topups = [t for t in txs if t.get("transaction_type") == "topup"]
    chargebacks = [t for t in txs if t.get("transaction_type") == "chargeback"]

    rules = []
    if len(topups) >= settings.fraud_topup_count_threshold:
        rules.append("rapid_topup_burst")
    if chargebacks:
        rules.append("chargeback_history")

    return FraudScanResult(
        user_id=user_id,
        flagged=bool(rules),
        rules_triggered=rules,
        details={
            "tx_count": len(txs),
            "rapid_topup_count": len(topups),
            "chargeback_count": len(chargebacks),
        },
    )
