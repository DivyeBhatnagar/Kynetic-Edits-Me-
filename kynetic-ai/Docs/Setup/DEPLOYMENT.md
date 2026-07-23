# Kynetic AI — Production Deployment Playbook

This document details the infrastructure deployment workflows, Terraform IaC, Kubernetes configurations, CI/CD pipelines, and Cloudflare WAF setups required for **production deployment**.

---

## 1. Cloud Infrastructure (AWS Infrastructure as Code)

All AWS cloud infrastructure is managed via Terraform in `infra/terraform/`.

```
                  ┌─────────────────────────────────────────┐
                  │          Cloudflare CDN / WAF           │
                  └────────────────────┬────────────────────┘
                                       │ HTTPS / TLS 1.3
                                       ▼
                  ┌─────────────────────────────────────────┐
                  │       AWS Application Load Balancer     │
                  └────────────────────┬────────────────────┘
                                       │
                                       ▼
                  ┌─────────────────────────────────────────┐
                  │        AWS EKS Cluster (1.29)           │
                  │  - API Gateway, Microservices, Workers  │
                  └────────────────────┬────────────────────┘
                   ┌───────────────────┴───────────────────┐
                   ▼                                       ▼
       ┌───────────────────────┐               ┌───────────────────────┐
       │ AWS RDS PostgreSQL 15 │               │ AWS ElastiCache Redis │
       └───────────────────────┘               └───────────────────────┘
```

### Terraform Deployment
```bash
cd infra/terraform

# Initialize remote backend state
terraform init -backend-config="bucket=kynetic-terraform-state-prod"

# Plan deployment
terraform plan -var-file=environments/production.tfvars

# Apply deployment
terraform apply -var-file=environments/production.tfvars -auto-approve
```

---

## 2. Kubernetes Services & Helm Operators

Microservices are deployed to EKS namespace `kynetic-production`:

```bash
# Connect kubectl to production cluster
aws eks update-kubeconfig --region ap-south-1 --name kynetic-prod-eks

# Install External Secrets Operator
helm install external-secrets external-secrets/external-secrets -n external-secrets --create-namespace

# Apply secrets mapping and service manifests
kubectl apply -f infra/secrets/secret-mappings.yaml
kubectl apply -f infra/k8s/services/
kubectl apply -f infra/k8s/workers/
```

---

## 3. GitHub Actions CI/CD Pipeline (`.github/workflows/deploy.yml`)

```
[Push to main] ──► [Run Pytest Suite] ──► [Build ECR Images] ──► [Alembic DB Migrate] ──► [K8s Rolling Update]
```

Automated deployment triggers on every commit to `main`:
1. **CI Step**: Executes 170-test suite across unit, integration, financial, legal, and security suites.
2. **Build Step**: Builds Docker images tagged with Git commit SHA and pushes to AWS ECR.
3. **Migrate Step**: Runs `alembic upgrade head` job against RDS PostgreSQL.
4. **Deploy Step**: Performs zero-downtime rolling update across Kubernetes deployment pods.
