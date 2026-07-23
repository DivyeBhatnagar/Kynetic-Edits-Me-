"""
Phase 16 — Financial Operations & Compliance Hardening Tests

Tests:
  - Double-entry ledger balancing rule (sum(debit) == sum(credit))
  - Unbalanced double-entry transaction rejection
  - Helper posting builders (topup, 85/15 rental payout split)
  - Indian Sec 194O TDS tax withholding math (1% PAN vs 20% no-PAN)
  - US 1099 threshold tracking ($600 USD)
  - Chargeback dispute wallet freezing and resolution flows
  - Daily automated ledger reconciliation audit (zero drift vs drift detected)
  - Financial ORM models AST structure (LedgerEntry, Chargeback, TaxWithholding)
"""

import ast
from decimal import Decimal
import os
import uuid
import pytest

FINANCIAL_MODEL_PATH = os.path.join(
    os.path.dirname(__file__), "../../libs/db_models/financial_models.py"
)


# ---------------------------------------------------------------------------
# 1. ORM AST Tests
# ---------------------------------------------------------------------------

def _parse_model_source():
    with open(FINANCIAL_MODEL_PATH) as f:
        return ast.parse(f.read())


def _get_class_names(tree) -> set:
    return {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}


def _get_mapped_column_names(tree, class_name: str) -> set:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                n.target.id
                for n in node.body
                if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
            }
    return set()


class TestFinancialModelsAST:
    """Validate Financial ORM models AST structure."""

    @pytest.fixture(scope="class")
    def tree(self):
        return _parse_model_source()

    def test_required_classes_exist(self, tree):
        classes = _get_class_names(tree)
        for req in ["LedgerEntry", "Chargeback", "TaxWithholding", "ChargebackStatus", "TaxJurisdiction"]:
            assert req in classes, f"Class {req} missing in financial_models.py"

    def test_ledger_entry_columns(self, tree):
        cols = _get_mapped_column_names(tree, "LedgerEntry")
        req = {"id", "transaction_id", "account", "debit", "credit", "currency", "created_at"}
        missing = req - cols
        assert not missing, f"LedgerEntry missing columns: {missing}"

    def test_chargeback_columns(self, tree):
        cols = _get_mapped_column_names(tree, "Chargeback")
        req = {"id", "transaction_id", "user_id", "provider", "status", "amount", "currency", "opened_at"}
        missing = req - cols
        assert not missing, f"Chargeback missing columns: {missing}"

    def test_tax_withholding_columns(self, tree):
        cols = _get_mapped_column_names(tree, "TaxWithholding")
        req = {"id", "user_id", "payout_id", "jurisdiction", "gross_payout", "tax_rate_pct", "withheld_amount", "issued_at"}
        missing = req - cols
        assert not missing, f"TaxWithholding missing columns: {missing}"


# ---------------------------------------------------------------------------
# 2. Double-Entry Accounting Ledger Tests
# ---------------------------------------------------------------------------

class TestDoubleEntryLedger:
    """Validate double-entry accounting rules."""

    def test_balanced_transaction_passes(self):
        from services.wallet_billing_service.ledger import (
            LedgerPosting,
            record_double_entry_transaction,
        )

        txn_id = str(uuid.uuid4())
        postings = [
            LedgerPosting(account="assets:stripe", debit=Decimal("100.00"), credit=Decimal("0.00")),
            LedgerPosting(account="liabilities:user_wallet", debit=Decimal("0.00"), credit=Decimal("100.00")),
        ]
        entries = record_double_entry_transaction(txn_id, postings)
        assert len(entries) == 2
        assert entries[0]["debit"] == Decimal("100.00")
        assert entries[1]["credit"] == Decimal("100.00")

    def test_unbalanced_transaction_rejected(self):
        from services.wallet_billing_service.ledger import (
            LedgerPosting,
            record_double_entry_transaction,
            UnbalancedLedgerError,
        )

        txn_id = str(uuid.uuid4())
        postings = [
            LedgerPosting(account="assets:stripe", debit=Decimal("100.00"), credit=Decimal("0.00")),
            LedgerPosting(account="liabilities:user_wallet", debit=Decimal("0.00"), credit=Decimal("90.00")),
        ]
        with pytest.raises(UnbalancedLedgerError):
            record_double_entry_transaction(txn_id, postings)

    def test_rental_payout_split_postings(self):
        from services.wallet_billing_service.ledger import build_rental_payout_postings

        postings = build_rental_payout_postings(total_cost=Decimal("10.00"), host_share_pct=Decimal("0.85"))
        # Total debit = $10.00 (user wallet), Total credit = $8.50 (host) + $1.50 (platform)
        total_debit = sum(p.debit for p in postings)
        total_credit = sum(p.credit for p in postings)
        assert total_debit == Decimal("10.0000")
        assert total_credit == Decimal("10.0000")


# ---------------------------------------------------------------------------
# 3. Tax Withholding Tests
# ---------------------------------------------------------------------------

class TestTaxWithholdingEngine:
    """Validate Sec 194O Indian TDS and US 1099 logic."""

    def test_indian_tds_with_valid_pan(self):
        from services.wallet_billing_service.tax_withholding import calculate_indian_tds

        res = calculate_indian_tds(
            user_id="user_in_123",
            payout_id="pay_991",
            gross_payout_inr=Decimal("10000.00"),
            pan_number="ABCDE1234F",
        )
        assert res.tax_rate_pct == Decimal("1.00")
        assert res.withheld_amount == Decimal("100.00")
        assert res.net_payout == Decimal("9900.00")

    def test_indian_tds_without_pan_higher_rate(self):
        from services.wallet_billing_service.tax_withholding import calculate_indian_tds

        res = calculate_indian_tds(
            user_id="user_in_123",
            payout_id="pay_992",
            gross_payout_inr=Decimal("10000.00"),
            pan_number=None,
        )
        assert res.tax_rate_pct == Decimal("20.00")
        assert res.withheld_amount == Decimal("2000.00")
        assert res.net_payout == Decimal("8000.00")

    def test_us_1099_threshold_check(self):
        from services.wallet_billing_service.tax_withholding import check_us_1099_reporting_threshold

        assert check_us_1099_reporting_threshold(Decimal("550.00")) is False
        assert check_us_1099_reporting_threshold(Decimal("600.00")) is True
        assert check_us_1099_reporting_threshold(Decimal("1200.00")) is True


# ---------------------------------------------------------------------------
# 4. Chargeback & Reconciliation Tests
# ---------------------------------------------------------------------------

class TestChargebackAndReconciliation:
    """Validate dispute flows and reconciliation auditing."""

    def test_dispute_processing(self):
        from services.wallet_billing_service.chargeback_handler import (
            DisputeEventPayload,
            process_incoming_dispute,
            resolve_dispute,
        )

        payload = DisputeEventPayload(
            event_id="evt_disp_1",
            provider="stripe",
            transaction_id=str(uuid.uuid4()),
            user_id=str(uuid.uuid4()),
            amount=Decimal("50.00"),
        )
        res = process_incoming_dispute(payload)
        assert res.status == "opened"
        assert res.frozen_amount == Decimal("50.00")

        resolution = resolve_dispute(res.chargeback_id, "won")
        assert resolution["new_status"] == "won"

    def test_daily_reconciliation_audit_zero_drift(self):
        from services.wallet_billing_service.reconciliation_job import (
            run_daily_ledger_reconciliation_audit,
        )

        audit = run_daily_ledger_reconciliation_audit(
            stripe_provider_balance=Decimal("5000.00"),
            razorpay_provider_balance=Decimal("200000.00"),
            internal_stripe_ledger=Decimal("5000.00"),
            internal_razorpay_ledger=Decimal("200000.00"),
        )
        assert audit.has_drift is False
        assert audit.status == "RECONCILED_SUCCESS"

    def test_daily_reconciliation_audit_drift_detected(self):
        from services.wallet_billing_service.reconciliation_job import (
            run_daily_ledger_reconciliation_audit,
        )

        audit = run_daily_ledger_reconciliation_audit(
            stripe_provider_balance=Decimal("5000.00"),
            razorpay_provider_balance=Decimal("199000.00"),
            internal_stripe_ledger=Decimal("5000.00"),
            internal_razorpay_ledger=Decimal("200000.00"),
        )
        assert audit.has_drift is True
        assert audit.razorpay_drift == Decimal("1000.00")
        assert audit.status == "DRIFT_DETECTED"
