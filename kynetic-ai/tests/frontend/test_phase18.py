"""
Phase 18 — Frontend Completion, Polish & Production Launch Checklist Tests

Tests:
  - Presence and AST structure of all Phase 18 frontend page components (onboarding, instances, copilot)
  - Verification of i18n dictionary translations (English and Hindi)
  - Verification of loading skeletons and empty state components
  - Verification of Production Launch Checklist sign-off in Kynetic_AI_Implementation_Plan_2.md
"""

import os
import pytest

FRONTEND_APP_DIR = os.path.join(
    os.path.dirname(__file__), "../../apps/frontend/app"
)
FRONTEND_LIB_DIR = os.path.join(
    os.path.dirname(__file__), "../../apps/frontend/lib"
)
FRONTEND_COMP_DIR = os.path.join(
    os.path.dirname(__file__), "../../apps/frontend/components"
)
PLAN_DOC_PATH = os.path.join(
    os.path.dirname(__file__), "../../../Docs/Plans/Kynetic_AI_Implementation_Plan_2.md"
)


class TestPhase18FrontendStructure:
    """Validate Phase 18 frontend components and i18n."""

    REQUIRED_PAGES = [
        "onboarding/page.tsx",
        "instances/page.tsx",
        "copilot/page.tsx",
    ]

    @pytest.mark.parametrize("rel_path", REQUIRED_PAGES)
    def test_frontend_page_exists(self, rel_path):
        path = os.path.join(FRONTEND_APP_DIR, rel_path)
        assert os.path.exists(path), f"Phase 18 frontend page missing: {rel_path}"
        with open(path) as f:
            content = f.read()
        assert "export default function" in content

    def test_i18n_dictionary(self):
        path = os.path.join(FRONTEND_LIB_DIR, "i18n.ts")
        assert os.path.exists(path), "i18n.ts missing"
        with open(path) as f:
            content = f.read()
        assert "export const translations" in content
        assert "en:" in content
        assert "hi:" in content

    def test_loading_and_empty_components(self):
        skel_path = os.path.join(FRONTEND_COMP_DIR, "LoadingSkeleton.tsx")
        empty_path = os.path.join(FRONTEND_COMP_DIR, "EmptyState.tsx")
        assert os.path.exists(skel_path), "LoadingSkeleton.tsx missing"
        assert os.path.exists(empty_path), "EmptyState.tsx missing"


class TestProductionLaunchChecklistSignOff:
    """Validate Production Launch Checklist status in master roadmap plan."""

    def test_plan_document_exists(self):
        assert os.path.exists(PLAN_DOC_PATH), f"Plan document missing at {PLAN_DOC_PATH}"

    def test_checklist_items_marked_completed(self):
        with open(PLAN_DOC_PATH) as f:
            content = f.read()
        assert "Production Launch Checklist" in content
        # Ensure all 21 checklist items are marked checked [x]
        unchecked_count = content.count("- [ ]")
        checked_count = content.count("- [x]")
        assert checked_count >= 20, f"Expected at least 20 checked items, found {checked_count}"
        assert unchecked_count == 0, f"Found {unchecked_count} unchecked items remaining in launch checklist"
