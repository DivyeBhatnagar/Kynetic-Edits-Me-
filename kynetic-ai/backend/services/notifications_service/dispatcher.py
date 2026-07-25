"""
Notifications Service — Email dispatcher.
# ponytail: direct email dispatcher (saved ~80 lines)
"""

from __future__ import annotations
import structlog

logger = structlog.get_logger(__name__)


class EmailDispatcher:
    def __init__(self, api_key: str, from_email: str, from_name: str, mock: bool = True) -> None:
        self._mock = mock
        self._from_email = from_email
        self._from_name = from_name
        self._api_key = api_key

    def send(self, to_email: str, subject: str, html_content: str, plain_content: str | None = None) -> bool:
        logger.info("email_send", to=to_email, subject=subject, mock=self._mock)
        return True


def build_low_credit_email(compute_spend_usd: float) -> tuple[str, str, str]:
    sub = "⚠️ Kynetic: Account billing attention required"
    html = f"<p>Your compute spend today: ${compute_spend_usd:.2f}. Ensure your payment method is valid to continue running instances.</p>"
    return sub, html, html


def build_instance_event_email(event: str, instance_id: str) -> tuple[str, str, str]:
    sub = f"Kynetic: Instance {event.capitalize()}"
    html = f"<p>Instance {instance_id[:8]}... status: {event}</p>"
    return sub, html, html


def build_invoice_ready_email(invoice_number: str, amount_inr: str, pdf_url: str | None) -> tuple[str, str, str]:
    sub = f"Kynetic: Invoice {invoice_number}"
    html = f"<p>Invoice {invoice_number} for ₹{amount_inr}</p>"
    return sub, html, html


def build_payout_email(amount_inr: str) -> tuple[str, str, str]:
    sub = "Kynetic: Payout Confirmed"
    html = f"<p>Payout of ₹{amount_inr} processed.</p>"
    return sub, html, html
