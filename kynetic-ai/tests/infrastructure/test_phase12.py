"""
Phase 12 — Infrastructure, Deployment & Environments Tests

Tests:
  - ORM model source validation via AST parsing (no DB connection required)
  - Deployment status enum validation
  - Docker Compose service completeness and secret safety
  - Kubernetes manifest structure validation
  - Terraform variable completeness
  - Deploy workflow structure validation
"""

import ast
import os
import yaml
import pytest

# ---------------------------------------------------------------------------
# Infrastructure Model tests — AST-based, NO DB connection needed
# ---------------------------------------------------------------------------

INFRA_MODEL_PATH = os.path.join(
    os.path.dirname(__file__),
    "../../libs/db_models/infrastructure_models.py"
)


def _parse_model_source():
    with open(INFRA_MODEL_PATH) as f:
        return ast.parse(f.read())


def _get_class_names(tree) -> set:
    return {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}


def _get_enum_values(tree, class_name: str) -> dict:
    """Extract enum values from an enum class definition."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                n.targets[0].id: ast.literal_eval(n.value)
                for n in node.body
                if isinstance(n, ast.Assign)
            }
    return {}


def _get_mapped_column_names(tree, class_name: str) -> set:
    """Extract mapped_column attribute names from a model class.
    
    AnnAssign (annotated assignment like `x: Mapped[str] = ...`) uses
    .target (singular), not .targets like a regular Assign node.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                n.target.id
                for n in node.body
                if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
            }
    return set()


class TestDeploymentReleaseModel:
    """Test infrastructure model source structure via AST (no DB connection)."""

    @pytest.fixture(scope="class")
    def tree(self):
        return _parse_model_source()

    def test_required_classes_exist(self, tree):
        classes = _get_class_names(tree)
        for required in ["DeployStatus", "HealthStatus", "DeployEnvironment",
                          "DeploymentRelease", "EnvironmentConfig", "ServiceHealthCheck"]:
            assert required in classes, f"Class '{required}' not found in infrastructure_models.py"

    def test_deploy_status_enum_values(self, tree):
        values = _get_enum_values(tree, "DeployStatus")
        assert values.get("started") == "started"
        assert values.get("success") == "success"
        assert values.get("failed") == "failed"
        assert values.get("rolled_back") == "rolled_back"

    def test_deploy_environment_enum_values(self, tree):
        values = _get_enum_values(tree, "DeployEnvironment")
        assert values.get("staging") == "staging"
        assert values.get("production") == "production"
        assert values.get("dev") == "dev"

    def test_health_status_enum_values(self, tree):
        values = _get_enum_values(tree, "HealthStatus")
        assert values.get("healthy") == "healthy"
        assert values.get("degraded") == "degraded"
        assert values.get("unhealthy") == "unhealthy"

    def test_deployment_release_has_required_columns(self, tree):
        columns = _get_mapped_column_names(tree, "DeploymentRelease")
        required = {"id", "service_name", "image_tag", "environment",
                    "git_sha", "status", "started_at", "completed_at",
                    "error_message", "migration_revision"}
        missing = required - columns
        assert not missing, f"DeploymentRelease missing columns: {missing}"

    def test_environment_config_has_required_columns(self, tree):
        columns = _get_mapped_column_names(tree, "EnvironmentConfig")
        required = {"id", "environment", "key", "value",
                    "description", "set_by", "created_at", "superseded_at"}
        missing = required - columns
        assert not missing, f"EnvironmentConfig missing columns: {missing}"

    def test_service_health_check_has_required_columns(self, tree):
        columns = _get_mapped_column_names(tree, "ServiceHealthCheck")
        required = {"id", "service_name", "environment", "status",
                    "response_time_ms", "checked_at", "details"}
        missing = required - columns
        assert not missing, f"ServiceHealthCheck missing columns: {missing}"

    def test_no_secret_storage_in_environment_config(self, tree):
        """EnvironmentConfig docstring must warn about not storing secrets."""
        with open(INFRA_MODEL_PATH) as f:
            source = f.read()
        assert "MUST NOT store secrets" in source or "not store secrets" in source.lower(), (
            "EnvironmentConfig class must contain explicit warning against storing secrets"
        )


# ---------------------------------------------------------------------------
# Docker Compose completeness tests
# ---------------------------------------------------------------------------

DOCKER_COMPOSE_PATH = os.path.join(
    os.path.dirname(__file__), "../../infra/docker-compose.yml"
)

EXPECTED_SERVICES = [
    "postgres",
    "redis",
    "api_gateway",
    "auth_service",
    "host_service",
    "marketplace_service",
    "wallet_billing_service",
    "provisioning_service",
    "security_service",
    "ai_router_service",
    "reputation_pricing_service",
    "notifications_service",
    "monitoring_service",
]


class TestDockerComposeCompleteness:
    """Ensure docker-compose.yml includes all required services."""

    @pytest.fixture(scope="class")
    def compose_config(self):
        with open(DOCKER_COMPOSE_PATH) as f:
            return yaml.safe_load(f)

    def test_compose_file_parses(self, compose_config):
        assert compose_config is not None
        assert "services" in compose_config

    def test_all_services_present(self, compose_config):
        defined_services = set(compose_config["services"].keys())
        missing = [s for s in EXPECTED_SERVICES if s not in defined_services]
        assert not missing, (
            f"Missing services in docker-compose.yml: {missing}"
        )

    def test_all_services_have_healthchecks_or_restart_policy(self, compose_config):
        """Services should have restart: unless-stopped for local resilience."""
        infra_services = {"postgres", "redis"}
        for service_name, service_config in compose_config["services"].items():
            if service_name in infra_services:
                continue
            if "worker" in service_name or "beat" in service_name or service_name == "migrate":
                continue  # Workers don't need restart for this check
            assert service_config.get("restart") == "unless-stopped", (
                f"Service '{service_name}' missing restart: unless-stopped"
            )

    def test_all_services_have_volumes_for_hot_reload(self, compose_config):
        """All FastAPI services should mount libs/ for hot reload."""
        skip = {"postgres", "redis", "migrate", "celery_beat"}
        for service_name, service_config in compose_config["services"].items():
            if service_name in skip or "worker" in service_name:
                continue
            volumes = service_config.get("volumes", [])
            has_libs = any("libs" in str(v) for v in volumes)
            assert has_libs, (
                f"Service '{service_name}' does not mount ./libs for hot reload"
            )

    def test_no_hardcoded_production_secrets(self, compose_config):
        """Verify no obviously live secrets are in the compose file."""
        import json
        compose_str = json.dumps(compose_config)
        forbidden_patterns = ["sk_live_", "rk_live_", "AKIA"]
        for pattern in forbidden_patterns:
            assert pattern not in compose_str, (
                f"Potential production secret pattern '{pattern}' found in docker-compose.yml"
            )


# ---------------------------------------------------------------------------
# K8s Manifest structure tests
# ---------------------------------------------------------------------------

K8S_PATH = os.path.join(os.path.dirname(__file__), "../../infra/k8s")


class TestKubernetesManifests:
    """Validate key properties of K8s manifests."""

    def _load_yaml_all(self, path: str):
        """Load all YAML documents from a file."""
        with open(path) as f:
            return list(yaml.safe_load_all(f))

    def test_namespace_file_exists(self):
        assert os.path.exists(os.path.join(K8S_PATH, "namespace.yaml"))

    def test_ingress_file_exists(self):
        assert os.path.exists(os.path.join(K8S_PATH, "ingress.yaml"))

    def test_api_gateway_deployment_has_hpa(self):
        docs = self._load_yaml_all(os.path.join(K8S_PATH, "services/api-gateway.yaml"))
        kinds = {d["kind"] for d in docs if d}
        assert "HorizontalPodAutoscaler" in kinds, "API Gateway must have an HPA"

    def test_api_gateway_deployment_has_zero_downtime_strategy(self):
        docs = self._load_yaml_all(os.path.join(K8S_PATH, "services/api-gateway.yaml"))
        deployment = next((d for d in docs if d and d["kind"] == "Deployment"), None)
        assert deployment is not None
        strategy = deployment["spec"]["strategy"]
        assert strategy["type"] == "RollingUpdate"
        assert strategy["rollingUpdate"]["maxUnavailable"] == 0, (
            "maxUnavailable must be 0 for zero-downtime deploys"
        )

    def test_api_gateway_has_prometheus_annotations(self):
        docs = self._load_yaml_all(os.path.join(K8S_PATH, "services/api-gateway.yaml"))
        deployment = next((d for d in docs if d and d["kind"] == "Deployment"), None)
        pod_annotations = deployment["spec"]["template"]["metadata"]["annotations"]
        assert pod_annotations.get("prometheus.io/scrape") == "true"

    def test_provisioning_service_has_higher_hpa_max(self):
        """Provisioning must have higher max replicas than api-gateway due to burstiness."""
        api_docs = self._load_yaml_all(os.path.join(K8S_PATH, "services/api-gateway.yaml"))
        prov_docs = self._load_yaml_all(os.path.join(K8S_PATH, "services/provisioning-service.yaml"))

        api_hpa = next((d for d in api_docs if d and d["kind"] == "HorizontalPodAutoscaler"), None)
        prov_hpa = next((d for d in prov_docs if d and d["kind"] == "HorizontalPodAutoscaler"), None)

        assert api_hpa and prov_hpa
        assert prov_hpa["spec"]["maxReplicas"] > api_hpa["spec"]["maxReplicas"], (
            "Provisioning service must scale to more replicas than API Gateway"
        )

    def test_db_migrate_job_has_deadline(self):
        docs = self._load_yaml_all(os.path.join(K8S_PATH, "jobs/db-migrate.yaml"))
        job = next((d for d in docs if d and d["kind"] == "Job"), None)
        assert job is not None
        assert job["spec"].get("activeDeadlineSeconds") is not None, (
            "db-migrate Job must have an activeDeadlineSeconds to prevent hanging"
        )

    def test_celery_workers_have_spot_toleration(self):
        docs = self._load_yaml_all(os.path.join(K8S_PATH, "workers/celery-workers.yaml"))
        deployments = [d for d in docs if d and d["kind"] == "Deployment"]
        # Check non-beat deployments have SPOT toleration
        for deploy in deployments:
            name = deploy["metadata"]["name"]
            if "beat" in name:
                continue  # Beat runs on regular nodes
            tolerations = deploy["spec"]["template"]["spec"].get("tolerations", [])
            has_spot = any(
                t.get("key") == "dedicated" and t.get("value") == "worker"
                for t in tolerations
            )
            assert has_spot, (
                f"Celery worker '{name}' must have SPOT node toleration"
            )


# ---------------------------------------------------------------------------
# Terraform variable completeness tests
# ---------------------------------------------------------------------------

TERRAFORM_VARS_PATH = os.path.join(
    os.path.dirname(__file__), "../../infra/terraform/variables.tf"
)

REQUIRED_VARIABLES = [
    "environment",
    "aws_region",
    "db_password",
    "db_instance_class",
    "redis_node_type",
    "cloudflare_zone_id",
    "cloudflare_api_token",
]


class TestTerraformVariables:
    """Verify Terraform variables.tf declares all required inputs."""

    def test_variables_file_exists(self):
        assert os.path.exists(TERRAFORM_VARS_PATH), "variables.tf must exist"

    def test_all_required_variables_declared(self):
        with open(TERRAFORM_VARS_PATH) as f:
            content = f.read()
        missing = [v for v in REQUIRED_VARIABLES if f'variable "{v}"' not in content]
        assert not missing, (
            f"Missing Terraform variables: {missing}"
        )

    def test_sensitive_variables_marked(self):
        with open(TERRAFORM_VARS_PATH) as f:
            content = f.read()
        # db_password, cloudflare_api_token, cloudflare_zone_id must be sensitive
        for var in ["db_password", "cloudflare_api_token", "cloudflare_zone_id"]:
            # Find variable block and check for sensitive = true
            var_start = content.find(f'variable "{var}"')
            if var_start == -1:
                continue
            var_block = content[var_start:var_start + 300]
            assert "sensitive   = true" in var_block or "sensitive = true" in var_block, (
                f"Variable '{var}' must be marked sensitive = true"
            )

    def test_environment_variable_has_validation(self):
        """Environment variable should have a validation block."""
        with open(TERRAFORM_VARS_PATH) as f:
            content = f.read()
        assert 'validation' in content, (
            "Terraform variables should include validation blocks"
        )


# ---------------------------------------------------------------------------
# Deploy workflow tests (GitHub Actions YAML validation)
# ---------------------------------------------------------------------------

DEPLOY_WORKFLOW_PATH = os.path.join(
    os.path.dirname(__file__), "../../.github/workflows/deploy.yml"
)


class TestDeployWorkflow:
    """Validate deploy workflow structure."""

    @pytest.fixture(scope="class")
    def workflow(self):
        with open(DEPLOY_WORKFLOW_PATH) as f:
            return yaml.safe_load(f)

    def test_workflow_file_exists(self):
        assert os.path.exists(DEPLOY_WORKFLOW_PATH)

    def test_workflow_has_staging_job(self, workflow):
        assert "deploy-staging" in workflow["jobs"], "Workflow must have deploy-staging job"

    def test_workflow_has_production_job(self, workflow):
        assert "deploy-production" in workflow["jobs"], "Workflow must have deploy-production job"

    def test_production_requires_staging_to_pass(self, workflow):
        prod_job = workflow["jobs"]["deploy-production"]
        needs = prod_job.get("needs", [])
        assert "deploy-staging" in needs, (
            "Production deploy must require staging to pass"
        )

    def test_workflow_has_concurrency_lock(self, workflow):
        assert "concurrency" in workflow, (
            "Deploy workflow must define concurrency group to prevent parallel deploys"
        )
        assert workflow["concurrency"].get("cancel-in-progress") is False, (
            "cancel-in-progress must be False — never cancel an in-progress deploy"
        )

    def test_workflow_has_failure_notification(self, workflow):
        assert "notify-failure" in workflow["jobs"], (
            "Workflow must have a failure notification job"
        )
