"""
Notifications Service — Email dispatcher.

Wraps SendGrid (or SMTP) for sending transactional emails.

MOCK_MODE (default: true):
  All sends are logged instead of dispatched — no real emails in dev/CI.

Templates are inline (Phase 10 MVP). In production, move to SendGrid
Dynamic Templates or a proper template service.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


class EmailDispatcher:
    """
    Sends transactional emails via SendGrid API or logs them in mock mode.

    Usage:
        dispatcher = EmailDispatcher(api_key="SG.xxx", mock=True)
        dispatcher.send(
            to_email="user@example.com",
            subject="Low balance",
            html_content="<p>Your wallet is running low.</p>",
        )
    """

    def __init__(self, api_key: str, from_email: str, from_name: str, mock: bool = True) -> None:
        self._mock = mock
        self._from_email = from_email
        self._from_name = from_name
        self._api_key = api_key
        self._sg = None

        if not mock:
            try:
                from sendgrid import SendGridAPIClient   # type: ignore[import]
                self._sg = SendGridAPIClient(api_key)
            except ImportError as e:
                raise RuntimeError(
                    "sendgrid package not installed. "
                    "Add it to requirements or set EMAIL_MOCK_MODE=true."
                ) from e

    def send(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        plain_content: str | None = None,
    ) -> bool:
        """Send an email. Returns True on success, False on failure."""
        if self._mock:
            logger.info(
                "email_mock_send",
                to=to_email,
                subject=subject,
                body_preview=html_content[:80],
            )
            return True

        try:
            from sendgrid.helpers.mail import Mail, Email, To, Content  # type: ignore[import]
            message = Mail(
                from_email=Email(self._from_email, self._from_name),
                to_emails=To(to_email),
                subject=subject,
                html_content=Content("text/html", html_content),
            )
            if plain_content:
                message.add_content(Content("text/plain", plain_content))
            response = self._sg.send(message)
            logger.info(
                "email_sent",
                to=to_email,
                subject=subject,
                status_code=response.status_code,
            )
            return response.status_code in (200, 202)
        except Exception as exc:
            logger.error("email_send_failed", to=to_email, subject=subject, error=str(exc))
            return False


# ── Email template builders ────────────────────────────────────────────────

def build_low_balance_email(balance_usd: float) -> tuple[str, str, str]:
    """Returns (subject, html, plain)."""
    subject = "⚠️ Kynetic: Your wallet balance is low"
    html = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: auto;">
      <h2 style="color: #1a1a2e;">Wallet Balance Low</h2>
      <p>Your Kynetic wallet balance is <strong>${balance_usd:.2f} USD</strong>.</p>
      <p>Running instances will be terminated if your balance reaches $0.</p>
      <a href="https://app.kynetic.ai/wallet"
         style="display:inline-block; background:#7c3aed; color:#fff;
                padding:10px 20px; border-radius:8px; text-decoration:none;">
        Top Up Now
      </a>
      <p style="color:#888; font-size:12px; margin-top:24px;">
        Kynetic — Compute Marketplace
      </p>
    </div>
    """
    plain = f"Your Kynetic wallet balance is ${balance_usd:.2f}. Top up at https://app.kynetic.ai/wallet"
    return subject, html, plain


def build_instance_event_email(event: str, instance_id: str) -> tuple[str, str, str]:
    """Returns (subject, html, plain) for instance lifecycle events."""
    event_label = {
        "started": "✅ Instance Started",
        "stopped": "⏸ Instance Stopped",
        "terminated": "🛑 Instance Terminated",
        "failed": "❌ Instance Failed",
    }.get(event, f"Instance Event: {event}")

    subject = f"Kynetic: {event_label}"
    html = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: auto;">
      <h2>{event_label}</h2>
      <p>Your instance <code>{instance_id[:8]}...</code> has {event}.</p>
      <a href="https://app.kynetic.ai/instances/{instance_id}"
         style="display:inline-block; background:#7c3aed; color:#fff;
                padding:10px 20px; border-radius:8px; text-decoration:none;">
        View Instance
      </a>
    </div>
    """
    plain = f"Your instance {instance_id} has {event}. View: https://app.kynetic.ai/instances/{instance_id}"
    return subject, html, plain


def build_invoice_ready_email(invoice_number: str, amount_inr: str, pdf_url: str | None) -> tuple[str, str, str]:
    """Returns (subject, html, plain) for GST invoice ready notifications."""
    subject = f"Kynetic: GST Invoice {invoice_number} Ready"
    dl_link = f'<a href="{pdf_url}">Download PDF</a>' if pdf_url else "PDF is being generated."
    html = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: auto;">
      <h2>GST Invoice Ready</h2>
      <p>Invoice <strong>{invoice_number}</strong> for ₹{amount_inr} has been generated.</p>
      <p>{dl_link}</p>
    </div>
    """
    plain = f"GST Invoice {invoice_number} for ₹{amount_inr}. {'Download: ' + pdf_url if pdf_url else 'PDF generating.'}"
    return subject, html, plain


def build_payout_email(amount_inr: str) -> tuple[str, str, str]:
    """Returns (subject, html, plain) for payout confirmation."""
    subject = "Kynetic: Payout Confirmed"
    html = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: auto;">
      <h2>Payout Confirmed</h2>
      <p>Your payout of ₹{amount_inr} has been initiated and will arrive in 1–2 business days.</p>
    </div>
    """
    plain = f"Your Kynetic payout of ₹{amount_inr} has been initiated."
    return subject, html, plain
