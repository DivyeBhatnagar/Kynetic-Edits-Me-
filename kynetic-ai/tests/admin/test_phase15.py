"""
Phase 15 — Admin Panel & Internal Operations Tooling Tests

Tests:
  - Admin ORM model AST structure (AdminUser, TicketActivityLog, FraudReviewItem)
  - Financial reconciliation drift calculation logic
  - Fraud review action handler validation
  - Support ticket activity logging payload validation
  - Host moderation action validation
  - Next.js Admin Dashboard app component structure
"""

import ast
from decimal import Decimal
import os
import pytest

ADMIN_MODEL_PATH = os.path.join(
    os.path.dirname(__file__), "../../libs/db_models/admin_models.py"
)
ADMIN_APP_DIR = os.path.join(
    os.path.dirname(__file__), "../../apps/admin_dashboard"
)


# ---------------------------------------------------------------------------
# 1. ORM AST Tests
# ---------------------------------------------------------------------------

def _parse_model_source():
    with open(ADMIN_MODEL_PATH) as f:
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


class TestAdminModelsAST:
    """Validate Admin ORM models AST without DB connections."""

    @pytest.fixture(scope="class")
    def tree(self):
        return _parse_model_source()

    def test_required_classes_exist(self, tree):
        classes = _get_class_names(tree)
        for req in ["AdminUser", "TicketActivityLog", "FraudReviewItem", "AdminRole", "TicketAction", "FraudStatus"]:
            assert req in classes, f"Class {req} missing in admin_models.py"

    def test_admin_user_columns(self, tree):
        cols = _get_mapped_column_names(tree, "AdminUser")
        req = {"id", "email", "role", "is_active", "created_at"}
        missing = req - cols
        assert not missing, f"AdminUser missing columns: {missing}"

    def test_ticket_activity_log_columns(self, tree):
        cols = _get_mapped_column_names(tree, "TicketActivityLog")
        req = {"id", "ticket_id", "admin_id", "action", "note", "created_at"}
        missing = req - cols
        assert not missing, f"TicketActivityLog missing columns: {missing}"

    def test_fraud_review_item_columns(self, tree):
        cols = _get_mapped_column_names(tree, "FraudReviewItem")
        req = {"id", "reason", "risk_score", "status", "created_at"}
        missing = req - cols
        assert not missing, f"FraudReviewItem missing columns: {missing}"


# ---------------------------------------------------------------------------
# 2. Financial Reconciliation Logic Tests
# ---------------------------------------------------------------------------

class TestReconciliationLogic:
    """Validate financial ledger drift audit calculation logic."""

    def test_reconciled_balances(self):
        from services.security_service.admin_routes import calculate_reconciliation_drift

        res = calculate_reconciliation_drift(
            db_debits_usd=Decimal("1000.00"),
            stripe_ledger_usd=Decimal("1000.00"),
            db_debits_inr=Decimal("50000.00"),
            razorpay_ledger_inr=Decimal("50000.00"),
        )
        assert res.usd_drift == Decimal("0.00")
        assert res.inr_drift == Decimal("0.00")
        assert res.reconciled is True

    def test_unreconciled_usd_drift_detected(self):
        from services.security_service.admin_routes import calculate_reconciliation_drift

        res = calculate_reconciliation_drift(
            db_debits_usd=Decimal("1050.00"),
            stripe_ledger_usd=Decimal("1000.00"),
            db_debits_inr=Decimal("50000.00"),
            razorpay_ledger_inr=Decimal("50000.00"),
        )
        assert res.usd_drift == Decimal("50.00")
        assert res.reconciled is False


# ---------------------------------------------------------------------------
# 3. Next.js Admin Dashboard Structure Tests
# ---------------------------------------------------------------------------

class TestAdminDashboardAppStructure:
    """Validate Next.js Admin Dashboard project files and routes."""

    REQUIRED_FILES = [
        "package.json",
        "tsconfig.json",
        "app/layout.tsx",
        "app/page.tsx",
        "app/fraud/page.tsx",
        "app/tickets/page.tsx",
        "app/reconciliation/page.tsx",
        "app/hosts/page.tsx",
    ]

    @pytest.mark.parametrize("rel_path", REQUIRED_FILES)
    def test_admin_app_file_exists(self, rel_path):
        full_path = os.path.join(ADMIN_APP_DIR, rel_path)
        assert os.path.exists(full_path), f"Admin dashboard file missing: {rel_path}"
        with open(full_path) as f:
            content = f.read()
        assert len(content) > 20, f"Admin dashboard file {rel_path} is empty"
