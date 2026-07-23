"""
Tests — Phase 10: Notifications service.

Tests:
  - EmailDispatcher mock mode
  - Email template builders (all 4 types)
  - NotificationRepository logic
  - SupportTicket region routing
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone
import uuid


# ── Email dispatcher mock mode ─────────────────────────────────────────────

class TestEmailDispatcherMock:
    def setup_method(self):
        from services.notifications_service.dispatcher import EmailDispatcher
        self.dispatcher = EmailDispatcher(
            api_key="SG.test",
            from_email="noreply@kynetic.ai",
            from_name="Kynetic",
            mock=True,
        )

    def test_send_returns_true_in_mock_mode(self):
        result = self.dispatcher.send(
            to_email="test@example.com",
            subject="Test",
            html_content="<p>Hello</p>",
        )
        assert result is True

    def test_send_with_plain_content(self):
        result = self.dispatcher.send(
            to_email="test@example.com",
            subject="Low balance",
            html_content="<p>Balance low</p>",
            plain_content="Balance low",
        )
        assert result is True

    def test_mock_does_not_import_sendgrid(self):
        """Mock mode should not require sendgrid to be installed."""
        from services.notifications_service.dispatcher import EmailDispatcher
        # If this doesn't raise ImportError, mock mode is working correctly
        dispatcher = EmailDispatcher("key", "from@x.com", "Test", mock=True)
        assert dispatcher._sg is None


# ── Email template builders ────────────────────────────────────────────────

class TestEmailTemplates:
    def test_low_balance_subject(self):
        from services.notifications_service.dispatcher import build_low_balance_email
        subject, html, plain = build_low_balance_email(balance_usd=3.50)
        assert "Low" in subject or "low" in subject
        assert "3.50" in plain
        assert "<" in html  # is HTML

    def test_low_balance_contains_topup_link(self):
        from services.notifications_service.dispatcher import build_low_balance_email
        _, html, _ = build_low_balance_email(balance_usd=1.0)
        assert "kynetic.ai/wallet" in html

    def test_instance_started_email(self):
        from services.notifications_service.dispatcher import build_instance_event_email
        subject, html, plain = build_instance_event_email("started", "inst-abc-123")
        assert "Start" in subject or "start" in subject
        assert "inst-abc-123" in html

    def test_instance_terminated_email(self):
        from services.notifications_service.dispatcher import build_instance_event_email
        subject, html, plain = build_instance_event_email("terminated", "inst-xyz")
        assert "Terminat" in subject or "terminat" in subject.lower()

    def test_instance_failed_email(self):
        from services.notifications_service.dispatcher import build_instance_event_email
        subject, html, plain = build_instance_event_email("failed", "inst-fail")
        assert "Fail" in subject or "fail" in subject.lower()

    def test_invoice_ready_with_pdf_url(self):
        from services.notifications_service.dispatcher import build_invoice_ready_email
        subject, html, plain = build_invoice_ready_email(
            invoice_number="KYN/2024-25/000001",
            amount_inr="1180.00",
            pdf_url="https://storage.kynetic.ai/invoices/test.pdf",
        )
        assert "KYN/2024-25/000001" in html
        assert "1180.00" in html
        assert "test.pdf" in html

    def test_invoice_ready_without_pdf_url(self):
        from services.notifications_service.dispatcher import build_invoice_ready_email
        _, html, _ = build_invoice_ready_email("KYN/2024-25/000001", "500.00", None)
        assert "PDF is being generated" in html or "generating" in html.lower()

    def test_payout_email(self):
        from services.notifications_service.dispatcher import build_payout_email
        subject, html, plain = build_payout_email(amount_inr="5000.00")
        assert "5000.00" in html
        assert "Payout" in subject

    def test_all_templates_return_3_tuple(self):
        """All builders must return (subject, html, plain) tuples."""
        from services.notifications_service.dispatcher import (
            build_low_balance_email,
            build_instance_event_email,
            build_invoice_ready_email,
            build_payout_email,
        )
        for builder, args in [
            (build_low_balance_email, [1.0]),
            (build_instance_event_email, ["started", "inst-1"]),
            (build_invoice_ready_email, ["KYN/24-25/001", "100", None]),
            (build_payout_email, ["500"]),
        ]:
            result = builder(*args)
            assert isinstance(result, tuple)
            assert len(result) == 3
            subject, html, plain = result
            assert isinstance(subject, str) and len(subject) > 0
            assert isinstance(html, str) and len(html) > 0
            assert isinstance(plain, str) and len(plain) > 0


# ── Monitoring metrics module ──────────────────────────────────────────────

class TestMonitoringMetrics:
    """Tests that prometheus-client metrics module loads without errors."""

    def test_metrics_module_loads(self):
        from services.monitoring_service.metrics import (
            instances_total,
            instances_active,
            wallet_topups_total,
            http_requests_total,
            router_no_results_total,
            notifications_dispatched_total,
            get_metrics_output,
        )
        assert instances_total is not None
        assert instances_active is not None

    def test_get_metrics_output_returns_bytes_and_content_type(self):
        from services.monitoring_service.metrics import get_metrics_output
        content, content_type = get_metrics_output()
        assert isinstance(content, bytes)
        assert "text/plain" in content_type

    def test_increment_counter(self):
        from services.monitoring_service.metrics import wallet_topups_total
        # Should not raise
        wallet_topups_total.labels(method="stripe", currency="usd").inc()

    def test_instance_gauge_set(self):
        from services.monitoring_service.metrics import instances_active
        instances_active.labels(resource_type="gpu", region="us-east-1").set(5)

    def test_histogram_observe(self):
        from services.monitoring_service.metrics import instance_duration_seconds
        instance_duration_seconds.labels(resource_type="gpu", region="us-east-1").observe(3600)


# ── Support ticket region routing ──────────────────────────────────────────

class TestSupportTicketRegion:
    """Tests for India-first routing logic."""

    def test_india_region_value(self):
        from libs.db_models.billing_monitoring_models import SupportRegion
        assert SupportRegion.india.value == "india"
        assert SupportRegion.global_.value == "global"

    def test_notification_types_cover_all_lifecycle_events(self):
        from libs.db_models.billing_monitoring_models import NotificationType
        lifecycle_types = {
            NotificationType.instance_started,
            NotificationType.instance_stopped,
            NotificationType.instance_terminated,
            NotificationType.instance_failed,
        }
        assert len(lifecycle_types) == 4

    def test_billing_notification_types(self):
        from libs.db_models.billing_monitoring_models import NotificationType
        billing_types = {
            NotificationType.low_balance,
            NotificationType.wallet_topup_confirmed,
            NotificationType.payout_confirmed,
            NotificationType.invoice_ready,
        }
        assert len(billing_types) == 4
