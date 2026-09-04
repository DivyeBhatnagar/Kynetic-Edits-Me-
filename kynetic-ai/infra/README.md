# Kynetic AI — Infrastructure & Deployment

This directory contains the production Infrastructure-as-Code (IaC), container orchestration manifests, observability configurations, and compute host automated onboarding scripts for Kynetic AI.

---

## 🏛️ Directory Structure

```
infra/
├── terraform/                # Multi-cloud Terraform configurations (AWS, GCP, Bare-Metal)
│   └── environments/         # Environment overlays (dev, staging, production)
├── k8s/                      # Kubernetes manifests
│   ├── services/             # Control plane FastAPI microservices & Gateway tunnel
│   ├── workers/              # Asynchronous Celery & background reconciliation workers
│   └── jobs/                 # Database migrations (Alembic) & routine batch jobs
├── host_install/             # Host Node Automated Setup Script & systemd templates
│   ├── install_host.sh       # One-line host onboarding installer
│   └── kynetic-agent.service # Systemd unit definition for kynetic-host-agent
├── observability/            # Full observability stack configurations
│   ├── loki/                 # Structured log aggregation configs
│   ├── alertmanager/         # PagerDuty & Slack alerting rules
│   ├── alertmanager-rules/   # PromQL alert definitions
│   └── grafana-dashboards/   # JSON definitions for Host, Service, & Financial dashboards
├── docker-compose.yml        # Complete local development stack
└── docker-compose.monitoring.yml # Local Prometheus + Grafana + Loki stack
```

---

## 🚀 Quick Deployment Options

### 1. Local Development Stack (Docker Compose)
Spins up all 11 microservices, Gateway Tunnel, PostgreSQL 16, and Redis 7:

```bash
docker compose -f infra/docker-compose.yml up -d
```

### 2. Observability Stack
Spins up Prometheus, Grafana, Loki, and Alertmanager:

```bash
docker compose -f infra/docker-compose.monitoring.yml up -d
```
Grafana will be accessible at `http://localhost:3001` (default admin credentials: `admin` / `kynetic_dev`).

### 3. Automated Compute Host Node Setup
To install the NVIDIA drivers, Firecracker VMM, containerd, eStargz snapshotter, and the Go Host Agent on an Ubuntu 22.04/24.04 server:

```bash
curl -fsSL https://get.kynetic.ai/host | sudo bash -s -- --token <HOST_AUTH_TOKEN>
```
