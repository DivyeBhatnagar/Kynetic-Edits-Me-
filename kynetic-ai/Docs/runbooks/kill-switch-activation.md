# Incident Runbook — Kill-Switch Activation & Recovery

## Trigger Conditions
- Alert: `SecurityKillSwitchTriggered`
- Triggered when an administrator invokes `POST /admin/kill-switch` to halt suspicious or compromised workloads/hosts.

## Immediate Response (T+0 to T+5m)
1. **Identify Target**: Check `kill_switch_events` table or `security_service` logs for `target_type` (`instance`, `host`, `account`) and `target_id`.
2. **Verify Halt Status**: Confirm target workload container or Firecracker MicroVM process has terminated.
3. **Notify On-Call**: Confirm alert has routed to Slack `#kynetic-ops-critical`.

## Investigation (T+5m to T+20m)
1. **Correlate Logs**: Use Loki query:
   ```logql
   {service_name="security_service"} |= "kill_switch"
   ```
2. **Review Security Event Log**: Query `security_event_logs` for preceding cryptomining, malware, or unverified binary execution events on the target.
3. **Assess Blast Radius**: Check if neighboring instances on the host are affected.

## Containment & Remediation
- **If Host Compromised**: Suspend host in `hosts` table (`status='suspended'`).
- **If Workload Malicious**: Issue cryptographic wipe receipt via `provisioning_service`.
- **If False Positive**: Re-enable target host or re-provision developer workload with credit compensation.

## Post-Incident
1. File Incident Record (`IncidentRecord` with severity `SEV1` or `SEV2`).
2. Conduct post-mortem review within 24 hours.
