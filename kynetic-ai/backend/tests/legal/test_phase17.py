"""
Phase 17 — Legal, Policy & Compliance Documentation Tests

Tests:
  - Presence and non-emptiness of all 6 legal & compliance documents
  - Verification of critical legal clauses (AUP prohibited workloads, 85/15 host split, DPDP Act, SOC 2 score)
  - Verification of frontend policy page components
"""

import os
import pytest

LEGAL_DOCS_DIR = os.path.join(
    os.path.dirname(__file__), "../../../Docs/legal"
)
FRONTEND_APP_DIR = os.path.join(
    os.path.dirname(__file__), "../../apps/frontend/app"
)


class TestLegalDocumentation:
    """Validate legal documents in Docs/legal/."""

    REQUIRED_DOCS = [
        ("terms-of-service-aup.md", ["Acceptable Use", "Cryptocurrency Mining", "Kill-Switch"]),
        ("privacy-policy.md", ["audit_logs", "device_fingerprints", "Zero Host File Access", "DPDP Act"]),
        ("host-agreement.md", ["85%", "15%", "98.0%", "Security & Liability Protection"]),
        ("refund-dispute-policy.md", ["Wallet Top-Up Refunds", "GST Credit Notes", "Chargeback"]),
        ("india-dpdp-compliance.md", ["DPDP Act 2023", "ap-south-1", "Section 194O"]),
        ("soc2-readiness-assessment.md", ["Security", "Availability", "Processing Integrity", "Readiness Score"]),
    ]

    @pytest.mark.parametrize("filename,keywords", REQUIRED_DOCS)
    def test_doc_exists_and_contains_keywords(self, filename, keywords):
        path = os.path.join(LEGAL_DOCS_DIR, filename)
        assert os.path.exists(path), f"Legal document missing: {filename}"
        with open(path) as f:
            content = f.read()
        assert len(content) > 300, f"Legal document {filename} is too short"
        for kw in keywords:
            assert kw in content, f"Legal document {filename} missing required clause: '{kw}'"


class TestFrontendPolicyRoutes:
    """Validate frontend public policy web components."""

    POLICY_PAGES = [
        "terms/page.tsx",
        "privacy/page.tsx",
    ]

    @pytest.mark.parametrize("rel_path", POLICY_PAGES)
    def test_frontend_policy_page_exists(self, rel_path):
        path = os.path.join(FRONTEND_APP_DIR, rel_path)
        assert os.path.exists(path), f"Frontend policy page missing: {rel_path}"
        with open(path) as f:
            content = f.read()
        assert "export default function" in content
        assert "metadata" in content
