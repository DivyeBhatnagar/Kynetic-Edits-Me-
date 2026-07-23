# Incident Runbook — RDS PostgreSQL Failover & Pool Recovery

## Trigger Conditions
- Alert: `DatabaseConnectionPoolExhaustion` or API 5xx spike due to DB connection failure.

## Immediate Response (T+0 to T+5m)
1. **Check AWS RDS Status**: Verify if RDS primary instance has initiated Multi-AZ automatic failover.
2. **Check App Error Rate**: Monitor `http_requests_total{status="500"}` across all services.
3. **Verify Pool Health**: SQLAlchemy async engine `pool_pre_ping=True` will automatically reconnect after failover completes (typically 30–60s).

## Recovery & Verification
1. **Verify New Primary**:
   ```bash
   aws rds describe-db-instances --db-instance-identifier kynetic-production --query "DBInstances[0].Status"
   ```
2. **Verify Alembic State**:
   ```bash
   kubectl exec -it deployment/api-gateway -n kynetic-production -- alembic current
   ```
3. **Check Connection Pools**: Monitor Grafana metric `kynetic_db_active_connections`.

## Post-Incident
1. Log incident in `incident_records` table with severity `SEV2`.
2. Inspect slow queries and pool sizing if failover was load-induced.
