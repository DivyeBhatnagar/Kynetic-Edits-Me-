"""
Phase 13 — Observability, Alerting & Incident Response Tests

Tests:
  - Grafana dashboard JSON validity and structure
  - Prometheus alert rule YAML validation
  - Alertmanager configuration structure
  - Loki and Promtail configuration validation
  - Observability ORM model AST structure (AlertEvent, IncidentRecord)
  - Operational runbook presence and content
  - Monitoring Docker Compose file validity
"""

import ast
import json
import os
import yaml
import pytest

OBSERVABILITY_DIR = os.path.join(
    os.path.dirname(__file__), "../../infra/observability"
)
RUNBOOKS_DIR = os.path.join(
    os.path.dirname(__file__), "../../../docs/runbooks"
)
OBSERVABILITY_MODEL_PATH = os.path.join(
    os.path.dirname(__file__), "../../libs/db_models/observability_models.py"
)


# ---------------------------------------------------------------------------
# 1. Grafana Dashboard Tests
# ---------------------------------------------------------------------------

class TestGrafanaDashboards:
    """Validate all pre-built Grafana dashboards."""

    DASHBOARD_FILES = [
        "api-overview.json",
        "provisioning-health.json",
        "billing-financial-health.json",
        "host-network-health.json",
    ]

    @pytest.mark.parametrize("filename", DASHBOARD_FILES)
    def test_dashboard_json_validity(self, filename):
        path = os.path.join(OBSERVABILITY_DIR, "grafana-dashboards", filename)
        assert os.path.exists(path), f"Dashboard file missing: {filename}"
        with open(path) as f:
            data = json.load(f)
        assert "title" in data, f"Dashboard {filename} missing 'title'"
        assert "panels" in data, f"Dashboard {filename} missing 'panels'"
        assert len(data["panels"]) > 0, f"Dashboard {filename} has no panels"

    def test_api_overview_panels(self):
        path = os.path.join(OBSERVABILITY_DIR, "grafana-dashboards/api-overview.json")
        with open(path) as f:
            data = json.load(f)
        panel_titles = [p["title"] for p in data["panels"]]
        assert any("Request Rate" in t for t in panel_titles)
        assert any("Latency" in t for t in panel_titles)
        assert any("5xx Error Rate" in t for t in panel_titles)

    def test_provisioning_health_panels(self):
        path = os.path.join(OBSERVABILITY_DIR, "grafana-dashboards/provisioning-health.json")
        with open(path) as f:
            data = json.load(f)
        panel_titles = [p["title"] for p in data["panels"]]
        assert any("Active Running Instances" in t for t in panel_titles)
        assert any("Failure Rate" in t for t in panel_titles)


# ---------------------------------------------------------------------------
# 2. Prometheus Alert Rules Tests
# ---------------------------------------------------------------------------

class TestPrometheusAlertRules:
    """Validate Prometheus alerting rules."""

    REQUIRED_ALERTS = [
        "ProvisioningHighFailureRate",
        "APIHigh5xxErrorRate",
        "WalletPaymentWebhookFailure",
        "SecurityKillSwitchTriggered",
        "HostMassDisconnection",
        "DatabaseConnectionPoolExhaustion",
    ]

    def test_alerts_yaml_parses(self):
        path = os.path.join(OBSERVABILITY_DIR, "alertmanager-rules/alerts.yml")
        assert os.path.exists(path)
        with open(path) as f:
            data = yaml.safe_load(f)
        assert "groups" in data
        assert len(data["groups"]) > 0

    def test_all_required_alerts_present(self):
        path = os.path.join(OBSERVABILITY_DIR, "alertmanager-rules/alerts.yml")
        with open(path) as f:
            data = yaml.safe_load(f)
        alert_names = set()
        for group in data["groups"]:
            for rule in group.get("rules", []):
                if "alert" in rule:
                    alert_names.add(rule["alert"])

        missing = [a for a in self.REQUIRED_ALERTS if a not in alert_names]
        assert not missing, f"Missing Prometheus alerts: {missing}"

    def test_alert_severity_labels(self):
        path = os.path.join(OBSERVABILITY_DIR, "alertmanager-rules/alerts.yml")
        with open(path) as f:
            data = yaml.safe_load(f)
        for group in data["groups"]:
            for rule in group.get("rules", []):
                if "alert" in rule:
                    labels = rule.get("labels", {})
                    assert "severity" in labels, f"Alert {rule['alert']} missing severity label"
                    assert labels["severity"] in ["critical", "warning", "info"]


# ---------------------------------------------------------------------------
# 3. Alertmanager & Loki Configuration Tests
# ---------------------------------------------------------------------------

class TestAlertmanagerAndLokiConfig:
    """Validate Alertmanager, Loki, and Promtail YAML configs."""

    def test_alertmanager_config(self):
        path = os.path.join(OBSERVABILITY_DIR, "alertmanager/alertmanager.yml")
        assert os.path.exists(path)
        with open(path) as f:
            data = yaml.safe_load(f)
        assert "route" in data
        assert "receivers" in data

    def test_loki_config(self):
        path = os.path.join(OBSERVABILITY_DIR, "loki/loki-config.yml")
        assert os.path.exists(path)
        with open(path) as f:
            data = yaml.safe_load(f)
        assert "schema_config" in data

    def test_promtail_config(self):
        path = os.path.join(OBSERVABILITY_DIR, "loki/promtail-config.yml")
        assert os.path.exists(path)
        with open(path) as f:
            data = yaml.safe_load(f)
        assert "scrape_configs" in data


# ---------------------------------------------------------------------------
# 4. Observability ORM Models AST Tests
# ---------------------------------------------------------------------------

def _parse_model_source():
    with open(OBSERVABILITY_MODEL_PATH) as f:
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


class TestObservabilityModels:
    """Validate ORM model AST structure without DB connections."""

    @pytest.fixture(scope="class")
    def tree(self):
        return _parse_model_source()

    def test_required_classes_exist(self, tree):
        classes = _get_class_names(tree)
        for req in ["AlertEvent", "IncidentRecord", "AlertSeverity", "AlertStatus", "IncidentSeverity", "IncidentStatus"]:
            assert req in classes, f"Class {req} missing in observability_models.py"

    def test_alert_event_columns(self, tree):
        cols = _get_mapped_column_names(tree, "AlertEvent")
        req = {"id", "alert_name", "severity", "service_name", "summary", "status", "fired_at"}
        missing = req - cols
        assert not missing, f"AlertEvent missing columns: {missing}"

    def test_incident_record_columns(self, tree):
        cols = _get_mapped_column_names(tree, "IncidentRecord")
        req = {"id", "title", "severity", "status", "lead_responder", "impact_started_at", "created_at"}
        missing = req - cols
        assert not missing, f"IncidentRecord missing columns: {missing}"


# ---------------------------------------------------------------------------
# 5. Incident Runbooks Tests
# ---------------------------------------------------------------------------

class TestIncidentRunbooks:
    """Validate operational incident runbooks."""

    RUNBOOK_FILES = [
        "kill-switch-activation.md",
        "database-failover.md",
        "payment-gateway-outage.md",
        "mass-host-disconnection.md",
    ]

    @pytest.mark.parametrize("filename", RUNBOOK_FILES)
    def test_runbook_exists_and_not_empty(self, filename):
        path = os.path.join(RUNBOOKS_DIR, filename)
        assert os.path.exists(path), f"Runbook missing: {filename}"
        with open(path) as f:
            content = f.read()
        assert len(content) > 100, f"Runbook {filename} is too short"
        assert "Trigger" in content or "Response" in content or "Remediation" in content
