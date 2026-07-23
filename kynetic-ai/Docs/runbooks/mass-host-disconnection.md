# Incident Runbook — Mass Host Heartbeat Disconnection

## Trigger Conditions
- Alert: `HostMassDisconnection`
- >20% of registered hosts lose heartbeat connectivity within 5 minutes.

## Immediate Response (T+0 to T+5m)
1. **Check WireGuard Relay**: Verify health of central WireGuard NAT relay host (`wireguard-relay`).
2. **Check Cloudflare / Network Transit**: Verify regional ISP routing issues or network transit outages in target region (e.g. India ap-south-1).
3. **Assess Affected Instances**: Query `instances` table for running instances on disconnected hosts.

## Remediation & Recovery
1. **Pause Marketplace Listings**: Temporarily pause automatic instance routing for affected host region to prevent failed deployments.
2. **Notify Affected Developers**: Trigger notification service email for impacted developers with running instances.
3. **Graceful Workload Migration**: For stateless workloads, offer automated migration to alternative available host nodes.

## Post-Incident
1. Update host reputation scores (`reputation_scores`) if host drop was unannounced host-side outage.
2. Log incident in `incident_records` (`SEV2` or `SEV3`).
