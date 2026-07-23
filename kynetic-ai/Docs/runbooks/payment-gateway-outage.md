# Incident Runbook — Payment Gateway Outage & Webhook Replay

## Trigger Conditions
- Alert: `WalletPaymentWebhookFailure`
- Razorpay or Stripe webhook processing failures or payment gateway outage.

## Immediate Response (T+0 to T+5m)
1. **Identify Gateway**: Check alert labels for provider (`Razorpay` or `Stripe`).
2. **Inspect Webhook Logs**:
   ```logql
   {service_name="wallet_billing_service"} |= "webhook"
   ```
3. **Verify Webhook Queue**: Check Celery dead-letter queue for failed webhook processing tasks.

## Mitigation
1. **Fallback Status**: Enable temporary manual verification banner in Developer Dashboard if gateway is down.
2. **Replay Webhooks**: Once gateway recovers, trigger webhook replay from payment provider dashboard or internal management CLI.
3. **Run Reconciliation Job**: Execute Celery task `reconcile_wallet_ledger` to detect any discrepancy between payment gateway transactions and DB wallets.

## Post-Incident
1. File Incident Record (`SEV2` if payment top-ups affected).
2. Audit GST invoice sequence continuity (`invoice_sequences`).
