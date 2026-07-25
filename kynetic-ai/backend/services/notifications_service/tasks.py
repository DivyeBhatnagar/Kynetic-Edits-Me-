"""
Notifications Service — Celery tasks.

Event-driven notifications triggered by:
  - Low wallet balance (provisioning service)
  - Instance lifecycle events (provisioning service)
  - GST invoice ready (billing service)
  - Payout confirmation (billing service)
"""

from __future__ import annotations

import uuid

import structlog

from services.notifications_service.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="services.notifications_service.tasks.dispatch_notification",
    bind=True,
    max_retries=3,
    default_retry_delay=15,
)
def dispatch_notification(
    self,
    user_id: str,
    notification_type: str,
    payload: dict,
) -> dict:
    """
    Core notification dispatch task.

    Steps:
      1. Lookup user email + notification preferences from DB
      2. Create in-app Notification record
      3. If email_enabled: send email via EmailDispatcher
      4. Mark notification as sent

    Called by any service that needs to notify a user:
      dispatch_notification.delay(
          user_id="...",
          notification_type="low_balance",
          payload={"balance_usd": 3.50},
      )
    """
    try:
        from sqlalchemy import create_engine, select
        from sqlalchemy.orm import Session
        from datetime import datetime, timezone

        from libs.db_models.billing_monitoring_models import (
            Notification,
            NotificationChannel,
            NotificationPreference,
            NotificationType,
        )
        from libs.db_models.user_models import User
        from services.notifications_service.config import get_settings
        from services.notifications_service.dispatcher import (
            EmailDispatcher,
            build_instance_event_email,
            build_invoice_ready_email,
            build_low_balance_email,
            build_payout_email,
        )

        settings = get_settings()
        sync_url = settings.database_url.replace("+asyncpg", "")
        engine = create_engine(sync_url, pool_pre_ping=True)

        _user_id = uuid.UUID(user_id)
        _ntype = NotificationType(notification_type)

        with Session(engine) as session:
            # Fetch user
            user = session.execute(
                select(User).where(User.id == _user_id)
            ).scalar_one_or_none()

            if not user:
                logger.warning("dispatch_notification_user_not_found", user_id=user_id)
                return {"skipped": "user_not_found"}

            # Fetch notification preferences
            pref = session.execute(
                select(NotificationPreference).where(NotificationPreference.user_id == _user_id)
            ).scalar_one_or_none()

            email_enabled = pref.email_enabled if pref else True

            # Build email content based on notification type
            email_sent = False
            subject, html, plain = "", "", ""

            if _ntype == NotificationType.low_balance:
                subject, html, plain = build_low_balance_email(
                    balance_usd=float(payload.get("balance_usd", 0))
                )
            elif _ntype in (
                NotificationType.instance_started,
                NotificationType.instance_stopped,
                NotificationType.instance_terminated,
                NotificationType.instance_failed,
            ):
                event = _ntype.value.replace("instance_", "")
                subject, html, plain = build_instance_event_email(
                    event=event,
                    instance_id=payload.get("instance_id", "unknown"),
                )
            elif _ntype == NotificationType.invoice_ready:
                subject, html, plain = build_invoice_ready_email(
                    invoice_number=payload.get("invoice_number", ""),
                    amount_inr=payload.get("amount_inr", "0"),
                    pdf_url=payload.get("pdf_url"),
                )
            elif _ntype == NotificationType.payout_confirmed:
                subject, html, plain = build_payout_email(
                    amount_inr=payload.get("amount_inr", "0")
                )
            else:
                subject = f"Kynetic: {_ntype.value.replace('_', ' ').title()}"
                html = f"<p>{payload.get('message', 'You have a new notification.')}</p>"
                plain = payload.get("message", "You have a new notification.")

            # Dispatch email
            if email_enabled and subject and user.email:
                dispatcher = EmailDispatcher(
                    api_key=settings.sendgrid_api_key,
                    from_email=settings.email_from_address,
                    from_name=settings.email_from_name,
                    mock=settings.email_mock_mode,
                )
                email_sent = dispatcher.send(
                    to_email=user.email,
                    subject=subject,
                    html_content=html,
                    plain_content=plain,
                )

            # Create in-app notification record
            now = datetime.now(timezone.utc)
            notif = Notification(
                id=uuid.uuid4(),
                user_id=_user_id,
                notification_type=_ntype,
                channel=NotificationChannel.in_app,
                title=subject or _ntype.value,
                body=plain or html,
                payload=payload,
                sent_at=now if email_sent else None,
            )
            session.add(notif)
            session.commit()

            logger.info(
                "notification_dispatched",
                user_id=user_id,
                notification_type=notification_type,
                email_sent=email_sent,
            )
            return {
                "notification_id": str(notif.id),
                "email_sent": email_sent,
                "user_id": user_id,
            }

    except Exception as exc:
        logger.error("dispatch_notification_failed", user_id=user_id, error=str(exc))
        raise self.retry(exc=exc)
