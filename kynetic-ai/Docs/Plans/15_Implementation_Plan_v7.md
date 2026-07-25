# Kynetic AI — Implementation Plan v7
## Marketplace Payment, Billing, Commission & Payout Architecture

---

# 1. Executive Summary

Kynetic's original billing design (Phases 1–10) treated payment as a two-party problem: developer pays, platform collects. That model breaks the moment a host needs to be paid their share — which is every single transaction on this marketplace. This document replaces it with a proper **three-party marketplace payment architecture** — Customer, Host, Kynetic — modeled on how Uber, Airbnb, and Stripe Connect actually move money, adapted for Kynetic's specific constraint: **usage is metered in real time, so the final charge amount is unknown at the moment payment is collected.**

That single constraint is the reason this architecture cannot simply bolt on Razorpay Route or Cashfree Easy Split's "auto-split at checkout" feature, the way a fixed-price booking marketplace would. Instead, this document separates **collection** (customer payments captured directly by the platform) from **settlement** (host earnings are calculated after usage ends and transferred separately, on a schedule) — using the same provider's *linked account + delayed transfer* capability rather than its instant-split capability. Every other component in this document — the ledger, commission engine, payout engine, host onboarding — is built around that one architectural decision.

---

# 2. Marketplace Payment Architecture

Three financial actors, three distinct money movements:

```
Customer Payment ─────► Kynetic Platform Account (payment gateway)
                                      │
                          (usage metering records USAGE_DEBIT in ledger)
                                      │
                          ┌───────────┴────────────┐
                          ▼                        ▼
                 Platform Commission        Host Earnings (ledger)
                 (retained, recognized          (accrued, pending
                  as revenue immediately)         settlement)
                                                    │
                                       (Payout Engine, scheduled)
                                                    ▼
                                     Provider Linked Account Transfer
                                                    │
                                                    ▼
                                          Host's Bank/UPI Account
```

**Why collection and settlement are decoupled:** A fixed-price marketplace (a ride, a night's stay) knows the total charge before money moves, so an instant split at checkout works. Kynetic doesn't know the final charge until the developer terminates the instance — could be 4 minutes or 40 hours later. So money enters the platform account first (via direct payment capture), usage is metered against the *double-entry ledger* (built in v7), and only *after* a billing session closes does that specific session's host-earnings portion become "transferable" — at which point the Payout Engine (Section 15) moves it out via the payment provider's **linked-account transfer API**, which both Razorpay Route and Cashfree Easy Split support as a distinct, delayed operation from order-time splitting.

---

# 3. Financial Data Flow (Full Lifecycle)

1. **Select GPU** — customer browses listings (existing marketplace service).
2. **Launch Instance** — customer requests an instance; system estimates cost using listing price × requested duration.
3. **Estimate Cost** — shown to the customer before commit; not yet a financial transaction.
4. **Create Payment Order** — a payment order is created (`POST /payments/order`) via the active Payment Provider Adapter for the estimated session cost.
5. **Gateway Processes Payment** — Kynetic's payment gateway creates a hosted checkout session (Razorpay Checkout / Stripe Payment Intent).
6. **Payment Success** — provider webhook (`payment.captured`) confirms funds landed in Kynetic's platform account; `CUSTOMER_PAYMENT` ledger entry is written.
7. **Provision Compute** — existing Provisioning Service flow (Phase 4) begins.
8. **Track Usage** — existing per-second metering (Implementation Plan v5, Phase 28) records `USAGE_DEBIT` entries in the double-entry ledger while `status = running`.
9. **Calculate Final Cost** — on termination, `billed_seconds` is finalized and host earnings split is calculated.
10. **Deduct Platform Commission** — Commission Engine (Section 9) computes the applicable rate for this specific transaction (host, GPU type, region, promo) and splits the final charge into `platform_commission` and `host_earnings` ledger entries (Section 7).
11. **Create Host Earnings** — a `host_earnings` ledger entry is created in `pending_settlement` status — money the host is owed but hasn't been transferred yet.
12. **Trigger Settlement** — the Payout Engine's scheduler (Section 15) picks up all `pending_settlement` earnings for a host once their configured payout cycle (daily/weekly/monthly) or minimum threshold is reached.
13. **Transfer Host Payout** — a Transfer request is issued to the host's provider Linked Account via the active adapter.
14. **Generate Invoice** — a GST-compliant (India) or standard (global) invoice is generated for the customer's completed billing session, and a separate payout statement is generated for the host.
15. **Close Billing** — the billing session (Section 5's state machine) moves to `completed`; the ledger is immutable from this point forward for that session.

---

# 4. Sequence Diagrams (Narrative)

### 4.1 Customer Payment → Direct Billing Ledger Entry
```
Customer → API: POST /payments/order {amount, currency}
API → Payment Provider Adapter: create_order()
Adapter → Provider (Razorpay/Cashfree): create order
Provider → API: order_id, checkout params
API → Customer: hosted checkout URL/params
Customer → Provider: completes payment (card/UPI)
Provider → API: webhook payment.captured (signed)
API → Webhook Handler: verify signature, verify not a replay
Billing API → Ledger Service: write CUSTOMER_PAYMENT entry
API → Ledger: write CUSTOMER_PAYMENT entry (Section 7)
```

### 4.2 Instance Termination → Commission Split → Pending Settlement
```
Billing Service (existing): finalize_billing(instance_id)
Billing Service → Commission Engine: resolve_commission_rate(host_id, gpu_type, region)
Commission Engine → Billing Service: commission_rate (e.g. 12%)
Billing Service → Ledger: write HOST_EARNINGS entry (net of commission)
Billing Service → Ledger: write PLATFORM_COMMISSION entry
Billing Service → host_earnings table: status = pending_settlement
```

### 4.3 Payout Engine → Provider Transfer → Host Bank Account
```
Payout Scheduler (Celery Beat) → Payout Engine: find hosts due for payout
Payout Engine → Ledger: sum pending_settlement earnings per host
Payout Engine → Payment Provider Adapter: create_transfer(linked_account_id, amount)
Adapter → Provider: Transfer API call
Provider → Adapter: transfer_id, status=processing
Payout Engine → payouts table: status = processing, provider_transfer_id
Provider → API: webhook payout.completed (or payout.failed)
API → Payout Engine: mark payout completed / trigger retry (Section 15)
API → Ledger: write PAYOUT entry, mark host_earnings rows as settled
```

### 4.4 Refund Flow
```
Support/Customer → API: POST /payments/refund {transaction_id, amount, reason}
API → Refund Validator: check refund eligibility (was compute actually delivered? Section 18)
API → Payment Provider Adapter: create_refund()
Adapter → Provider: Refund API call
Provider → API: webhook refund.processed
API → Ledger: write REFUND entry (reverses original CUSTOMER_PAYMENT proportionally)
Billing API → Ledger: debit refund_reserve if host was already paid (Section 18)
```

---

# 5. State Machines

### 5.1 Billing Session State Machine
```
draft → pending_payment → paid → provisioning → running ⇄ stopping
                                                          │
                                              calculating_charges
                                                          │
                                            settlement_pending
                                                          │
                                                    host_paid
                                                          │
                                                    completed

Failure branches (reachable from multiple states):
  pending_payment → payment_failed
  paid/provisioning/running → cancelled (refund path, Section 18)
  settlement_pending → payout_failed → (retry) → host_paid
  any state → chargeback (Section 18)
```

### 5.2 Payout State Machine
```
scheduled → processing → completed
                │
                └─► failed → retrying (max N attempts) → completed
                                  │
                                  └─► manual_review (after max attempts exhausted)
```

### 5.3 Host Onboarding State Machine (detailed in Section 13)
```
registered → identity_submitted → kyc_pending → kyc_approved → provider_account_created → active
                                        │
                                   kyc_rejected → (resubmit) → identity_submitted
```

---

# 6. Database Design

Extends the existing schema (`users`, `hosts`, `instances` from earlier phases) with the following new tables.

**`payment_provider_accounts`**
`id, host_id (FK→hosts), provider[razorpay|cashfree|stripe|adyen|wise], linked_account_id, account_status[pending|active|suspended], created_at, updated_at`
*(One host can have accounts across multiple providers over time — e.g., migrating from Razorpay to Stripe Connect for a host that relocates.)*

**`host_kyc_records`**
`id, host_id, pan_number_encrypted, pan_verified, bank_account_number_encrypted, ifsc_code, bank_verified, upi_id (nullable), document_urls (jsonb), status[pending|approved|rejected], rejection_reason, reviewed_by, reviewed_at`

**`orders`**
`id, user_id, provider, provider_order_id, amount, currency, purpose[direct_charge|session_payment], status[created|paid|failed|expired], created_at`

**`payments`**
`id, order_id (FK→orders), provider_payment_id, amount, currency, status[captured|failed|refunded], method[card|upi|netbanking], captured_at`

**`refunds`**
`id, payment_id (FK→payments), amount, currency, reason, status[pending|processed|failed], provider_refund_id, requested_by, processed_at`

**`billing_sessions`**
`id, instance_id (FK→instances), customer_id, host_id, status (Section 5.1 enum), estimated_cost, final_cost, currency, opened_at, closed_at`

**`usage_records`**
`id, billing_session_id, billed_seconds, rate_per_second, gross_amount, recorded_at` — append-only, one row per metering tick (or aggregated per minute for storage efficiency at scale).

**`commission_rules`**
`id, scope[global|host|enterprise|promotional|gpu_type|region|workload], scope_ref_id (nullable — host_id, gpu_model, region_id depending on scope), commission_pct, priority, valid_from, valid_until, created_by, active`

**`host_earnings`**
`id, billing_session_id, host_id, gross_amount, commission_amount, commission_rule_id (FK), net_amount, currency, status[pending_settlement|settled|held|reversed], created_at, settled_at`

**`payouts`**
`id, host_id, payout_cycle[daily|weekly|monthly|manual], total_amount, currency, status (Section 5.2 enum), provider_transfer_id, attempt_count, last_attempt_at, created_at, completed_at`

**`payout_line_items`**
`id, payout_id (FK→payouts), host_earnings_id (FK→host_earnings)` — join table so every payout is fully traceable back to the exact billing sessions it settled.

**`settlements`**
`id, payout_id (FK→payouts), provider_settlement_id, provider_fee, net_settled_amount, settled_at` — captures the provider's own settlement confirmation, distinct from the transfer initiation, since providers settle to the host's bank asynchronously after the transfer is accepted.

**`ledger_entries`** (extends Implementation Plan v2's double-entry design)
`id, entry_type[customer_payment|host_earnings|platform_commission|refund|chargeback|payout|adjustment|tax|fee|balance_correction], account, debit, credit, currency, reference_type[billing_session|payout|refund], reference_id, created_at`

**`tax_records`**
`id, billing_session_id (nullable), payout_id (nullable), tax_type[gst|tds|vat], rate_pct, amount, jurisdiction, created_at`

**`webhook_events`** (Section 12)
`id, provider, event_type, provider_event_id (unique constraint — replay protection), payload (jsonb), status[received|processed|failed], received_at, processed_at`

### Key Indexes
- `host_earnings (host_id, status)` — the Payout Engine's primary query.
- `ledger_entries (reference_type, reference_id)` — trace any transaction back through the ledger.
- `webhook_events (provider, provider_event_id)` UNIQUE — hard replay-protection constraint, not just application logic.
- `commission_rules (scope, scope_ref_id, active, priority)` — resolution query for the Commission Engine.

### ER Summary
```
hosts 1───* payment_provider_accounts
hosts 1───1 host_kyc_records
users 1───* orders 1───* payments 1───* refunds
instances 1───1 billing_sessions 1───* usage_records
billing_sessions 1───* host_earnings *───1 commission_rules
host_earnings *───1 payouts (via payout_line_items)
payouts 1───1 settlements
(all of the above) ──► ledger_entries (polymorphic reference)
```

---

# 7. Ledger Design

Every financial event produces one or more **balanced** double-entry `ledger_entries` rows — a debit somewhere is always matched by an equal credit somewhere else. This is the single source of truth for "where did the money actually go," independent of what any individual service's application-level tables claim.

**Core ledger accounts:**
- `customer_account:{user_id}`
- `platform_revenue`
- `host_payable:{host_id}`
- `tax_payable:{jurisdiction}`
- `refund_reserve`
- `provider_clearing` (funds in-transit at the payment provider, not yet settled to Kynetic's bank)

**Example — a ₹1,000 completed rental with 12% commission and 18% GST on the platform fee:**

| Entry | Account | Debit | Credit |
|---|---|---|---|
| Customer payment captured | `provider_clearing` / `customer_account:U1` | 1000 | 1000 |
| Usage metered | `customer_account:U1` / `platform_revenue` (gross) | 1000 | 1000 |
| Commission split | `platform_revenue` / `host_payable:H1` | 120 | 880 (net effect) |
| GST on platform commission | `platform_revenue` / `tax_payable:IN` | 21.60 | 21.60 |
| Payout executed | `host_payable:H1` / `provider_clearing` | 880 | 880 |

This structure means: **the sum of every host's `host_payable` balance plus `tax_payable` plus recognized `platform_revenue` must always equal total customer payments minus refunds** — a daily reconciliation job (Implementation Plan v2, Phase 16, extended here) asserts this identity and pages on-call the moment it doesn't hold.

**Immutability:** `ledger_entries` rows are never updated or deleted. A correction is always a new offsetting entry (`balance_correction` type), preserving a complete, auditable history — this is non-negotiable for any future financial audit or SOC 2 review.

---

# 8. Billing Engine

Supports every billing mode the marketplace needs, all built on the same underlying per-second metering primitive (Implementation Plan v5, Phase 28) so no mode requires a separate metering pipeline:

- **Per-second billing** (default): the base primitive — already built.
- **Per-minute / hourly billing**: presentation-layer rounding only (invoices display hourly-equivalent rates), underlying metering stays per-second for pricing fairness.
- **Prepaid billing**: current default — account must have a valid payment capture before `running` is reached (enforced by `_validate_account` in `validators.py`).
- **Postpaid billing** (future, enterprise only): a `credit_limit` field allows negative balance up to a configured ceiling — requires a credit risk/underwriting decision per enterprise account, explicitly gated behind manual approval, not self-serve.
- **Coupons / Promo Codes**: a `promo_codes` table (`code, discount_type[pct|flat], value, valid_from, valid_until, usage_limit, redeemed_count`) applied at payment or billing-session-close time, producing an additional `ledger_entries` row (`adjustment` type) so discounts are auditable, not silently absorbed into `platform_revenue`.
- **Taxes**: computed per jurisdiction (Section 6's `tax_records`), India GST at 18% on the platform's commission specifically (not on the full transaction — the host's earnings are the host's own tax responsibility, consistent with a marketplace facilitation model), with a pluggable tax-rule table so future jurisdictions (VAT for EU expansion) don't require code changes.
- **Overage Protection / Credit Limits**: the existing zero-balance auto-termination (Implementation Plan v5, Phase 28) is overage protection for prepaid accounts; postpaid accounts get a hard `credit_limit` ceiling enforced the same way.
- **Failed Payments**: an order that never reaches `payment.captured` never creates a `CUSTOMER_PAYMENT` ledger entry — no instance can be provisioned against an unconfirmed payment (enforced by the `_validate_account` check, no new logic needed there).
- **Cancelled Jobs**: covered by the existing `failed`/`cancelled` instance states — full hold refund, zero host earnings created (since no usage occurred).
- **Billing Retry**: a failed metering tick (Implementation Plan v5's `debit_running_instance`) retries with Celery's built-in exponential backoff; three consecutive failures escalate to a manual-review alert rather than silently dropping billing for that instance.

---

# 9. Commission Engine

**Design:** a rule-resolution engine, not a hardcoded percentage. `commission_rules` rows are evaluated in priority order at the moment a billing session closes, and the **first matching, still-valid rule wins** — allowing overrides without ever deleting the global default.

**Resolution order (highest priority first):**
1. **Promotional** (time-boxed, e.g., a launch promotion at 5% for the first 90 days) — `scope=promotional`
2. **Host-specific override** (negotiated rate for a strategic host) — `scope=host`
3. **Enterprise** (negotiated rate for a specific enterprise customer relationship) — `scope=enterprise`
4. **Workload-specific** (e.g., lower commission on long-running training jobs to encourage retention) — `scope=workload`
5. **GPU-type-specific** (e.g., higher commission on scarce H100 listings) — `scope=gpu_type`
6. **Region-specific** (e.g., a promotional rate for the India-first launch market) — `scope=region`
7. **Global default** — `scope=global`, always exists as the final fallback, never deletable, only ever superseded.

```python
# services/commission_service/resolver.py
async def resolve_commission_rate(db, host_id: str, gpu_model: str, region_id: str, is_enterprise: bool) -> Decimal:
    candidates = await fetch_active_rules_for(db, host_id, gpu_model, region_id, is_enterprise)
    candidates.sort(key=lambda r: r.priority)  # lower number = higher priority, evaluated first
    for rule in candidates:
        if rule.valid_from <= now() <= (rule.valid_until or FAR_FUTURE):
            return rule.commission_pct
    return await get_global_default_rate(db)  # guaranteed to exist
```

**Auditability:** every `host_earnings` row stores the exact `commission_rule_id` that was applied — so a host disputing their payout can be shown precisely which rule fired and why, not just a final number.

---

# 10. Payment Provider Abstraction

```python
# services/payment_service/provider_interface.py
from abc import ABC, abstractmethod
from decimal import Decimal

class PaymentProviderInterface(ABC):
    @abstractmethod
    async def create_order(self, amount: Decimal, currency: str, metadata: dict) -> "OrderResult": ...

    @abstractmethod
    async def verify_webhook_signature(self, payload: bytes, signature: str) -> bool: ...

    @abstractmethod
    async def create_linked_account(self, host_kyc: dict) -> "LinkedAccountResult": ...

    @abstractmethod
    async def create_transfer(self, linked_account_id: str, amount: Decimal, currency: str, reference_id: str) -> "TransferResult": ...

    @abstractmethod
    async def create_refund(self, payment_id: str, amount: Decimal, reason: str) -> "RefundResult": ...
```

**Adapters:** `RazorpayRouteAdapter`, `CashfreeEasySplitAdapter` implemented against this shared interface today; `StripeConnectAdapter` (global expansion), `AdyenAdapter`, `WiseAdapter` (cross-border host payouts) are pure additions later — **no existing service code changes when a new adapter is added**, only a new class implementing the same interface plus a config entry mapping which provider serves which host's country/currency.

```python
# services/payment_service/provider_factory.py
def get_provider_for_host(host: Host) -> PaymentProviderInterface:
    if host.country_code == "IN":
        return RazorpayRouteAdapter()  # or CashfreeEasySplitAdapter() per config
    return StripeConnectAdapter()  # future — global hosts
```

This factory pattern is the entire point of the abstraction: **business logic (Billing Engine, Payout Engine, Commission Engine) never imports a provider SDK directly, only this interface.**

---

# 11. API Specification

| Endpoint | Method | Purpose |
|---|---|---|
| `/v1/payments/order` | POST | Create a payment order for compute session (idempotency-key required) |
| `/v1/payments/webhook/{provider}` | POST | Provider webhook receiver (Section 12) |
| `/v1/payments/refund` | POST | Initiate a refund (admin/support-gated) |
| `/v1/hosts/onboard` | POST | Begin host onboarding (Section 13) |
| `/v1/hosts/{id}/kyc` | POST | Submit KYC documents |
| `/v1/hosts/{id}/kyc/status` | GET | Current KYC status |
| `/v1/billing/session/{instance_id}` | GET | Live billing session state + running cost |
| `/v1/billing/close` | POST | Internal — closes a billing session (called by Billing Service, not developer-facing) |
| `/v1/payouts/create` | POST | Admin-triggered manual payout (Section 15) |
| `/v1/payouts` | GET | Host's payout history |
| `/v1/ledger` | GET | Admin-only — raw ledger query, paginated, filterable by account/date |
| `/v1/invoices` | GET | Customer/host invoice list |
| `/v1/invoices/{id}` | GET | Single invoice detail + PDF URL |
| `/v1/transactions` | GET | Ledger transaction history (customer-facing) |

All mutating endpoints require `Idempotency-Key`; all responses follow the shared error envelope (Implementation Plan v14, Section 6); pagination is cursor-based throughout.

---

# 12. Webhook Architecture

**Signature Verification:** every provider webhook (Razorpay, Cashfree, and future adapters) is verified against its HMAC signature *before* any payload field is trusted or parsed — a failed signature check returns `400` immediately and is logged as a potential attack, not silently ignored.

**Replay Protection:** the `webhook_events.provider_event_id` unique constraint (Section 6) makes replay protection a database-level guarantee, not just application logic — a duplicate webhook delivery (which every provider explicitly warns can happen) is a no-op insert conflict, handled gracefully, never double-processed.

**Retries & Dead Letter Queue:** webhook *processing* (not receipt) runs as a Celery task; a processing failure (e.g., a transient DB outage) retries with exponential backoff up to 5 times, then moves to a dead-letter queue (`webhook_events.status = failed`) surfaced on the Admin Dashboard (Section 17) for manual intervention — the webhook HTTP response to the provider is still `200 OK` immediately on *receipt* (not processing completion), since providers will retry-storm an endpoint that doesn't ack quickly.

**Events Handled:** `payment.captured`, `payment.failed`, `refund.processed`, `settlement.processed`, `payout.completed`, `payout.failed`, `kyc.approved`, `kyc.rejected`, `linked_account.updated`.

```python
# services/payment_service/webhook_handler.py
@router.post("/payments/webhook/{provider}")
async def receive_webhook(provider: str, request: Request):
    raw_body = await request.body()
    signature = request.headers.get("X-Webhook-Signature")
    adapter = get_adapter(provider)
    if not await adapter.verify_webhook_signature(raw_body, signature):
        logger.warning("webhook_signature_invalid", provider=provider)
        raise HTTPException(400, "Invalid signature")

    event = parse_event(raw_body)
    inserted = await try_insert_webhook_event(provider, event.id, event.payload)  # unique constraint gate
    if not inserted:
        return {"status": "duplicate_ignored"}  # replay — already processed

    process_webhook_event.delay(provider, event.id)  # async Celery task, retried on failure
    return {"status": "received"}
```

---

# 13. Host Onboarding

```
registered
    │  (host signs up, existing Phase 1 auth)
    ▼
identity_submitted
    │  POST /hosts/{id}/kyc — PAN, bank account, UPI (optional), documents
    ▼
kyc_pending
    │  submitted to provider's KYC verification (Razorpay Route / Cashfree onboarding API)
    ▼
   ┌────────────┴────────────┐
   ▼                          ▼
kyc_approved              kyc_rejected
   │                          │  (host notified with reason, resubmits → identity_submitted)
   ▼
provider_account_created
   │  create_linked_account() called via active adapter (Section 10)
   ▼
terms_accepted
   │  host explicitly accepts marketplace + payout terms (legal requirement, logged with timestamp)
   ▼
active — host can now list hardware and receive payouts
```

**APIs involved:** `POST /hosts/{id}/kyc` (internal) → provider's KYC submission endpoint (external, via adapter) → provider webhook `kyc.approved`/`kyc.rejected` (Section 12) → internal `create_linked_account()` call → `payment_provider_accounts` row created with `account_status = active`.

**Database tables involved:** `host_kyc_records`, `payment_provider_accounts`, plus the existing `hosts.status` field gains new valid values (`kyc_pending`, `kyc_rejected`, `payout_ready`) layered alongside its existing hardware-verification states from Phase 2 — a host can be hardware-verified and payout-pending simultaneously; these are two independent state tracks (hardware trust vs. financial trust) that both must reach "ready" before a listing can go live and actually earn money.

---

# 14. Marketplace Account Model

Every host's financial identity is represented by these fields (spread across `hosts`, `host_kyc_records`, and `payment_provider_accounts` per Section 6, unified here conceptually):

| Field | Purpose |
|---|---|
| Internal Host ID | Kynetic's own primary key (`hosts.id`) — never exposed to any external provider |
| Marketplace Account ID | A stable, provider-agnostic identifier Kynetic controls, mapped internally to whichever `payment_provider_accounts` row is currently active — this is what allows a host to migrate providers without their earnings history fragmenting |
| Payment Provider Account ID | The provider's own linked-account identifier (`linked_account_id`) — provider-specific, can change if migrated |
| Settlement Status | Derived from open `host_earnings` rows — `no_pending_earnings` / `pending_settlement` / `settlement_in_progress` |
| KYC Status | `host_kyc_records.status` |
| Bank Verification | `host_kyc_records.bank_verified` — confirmed via provider's penny-drop or equivalent verification, not just format-validated |
| Payout Preferences | `payout_cycle` (daily/weekly/monthly), minimum payout threshold, preferred currency |
| Risk Score | Feeds from the same fraud/reputation signals as Security Plan v3 and Implementation Plan v2's fraud detection — a high-risk host may be forced onto a longer settlement delay (Section 15) before their first several payouts, a standard marketplace risk-mitigation pattern |
| Country | Determines which provider adapter serves this host (Section 10's factory) and which tax regime applies |
| Tax Information | PAN (India), GSTIN if the host is GST-registered as a business, future equivalents (SSN/EIN, VAT number) for other geographies |
| Verification Documents | Stored as encrypted references (`document_urls`) — the documents themselves live in access-controlled object storage, never inline in the database |

---

# 15. Settlement & Payout Engine

**Scheduling:** Celery Beat runs the Payout Scheduler daily; each host's actual payout cadence (`daily|weekly|monthly|manual`) determines whether *this specific run* actually triggers a transfer for them, or just accumulates further.

**Minimum Payout Threshold:** a host with pending earnings below their configured minimum (e.g., ₹500) simply rolls forward to the next cycle rather than triggering a tiny, fee-inefficient transfer — configurable per-host, with a sane platform-wide default.

**Idempotency:** every payout attempt carries a Kynetic-generated `reference_id` (the `payouts.id`) passed to the provider's Transfer API as an idempotency key — if a retry occurs (Section 15's failure handling below) after a network timeout where Kynetic isn't sure the first attempt succeeded, the provider itself de-duplicates based on that same reference, preventing a host from ever being paid twice for one settlement batch.

**Failure Recovery:**
```python
# services/payout_service/payout_engine.py
@shared_task(bind=True, max_retries=5)
def execute_payout(self, payout_id: str):
    payout = get_payout(payout_id)
    adapter = get_provider_for_host(payout.host)
    try:
        result = adapter.create_transfer(
            linked_account_id=payout.host.linked_account_id,
            amount=payout.total_amount,
            currency=payout.currency,
            reference_id=payout.id,  # idempotency key at the provider
        )
        update_payout_status(payout_id, "processing", provider_transfer_id=result.transfer_id)
    except ProviderTransientError as e:
        raise self.retry(exc=e, countdown=2 ** self.request.retries * 60)
    except ProviderPermanentError as e:
        update_payout_status(payout_id, "manual_review", failure_reason=str(e))
        notify_finance_team(payout_id, reason=str(e))
```

**Reconciliation:** a daily job compares `payouts.total_amount` (what Kynetic believes it sent) against `settlements.net_settled_amount` (what the provider confirms actually settled, net of provider fees) — any mismatch beyond an expected fee-rounding tolerance pages finance/on-call, extending the same reconciliation discipline already established for the customer-side ledger (Section 7).

**Payout History:** fully reconstructable per host via `payouts ⋈ payout_line_items ⋈ host_earnings ⋈ billing_sessions` — a host can always trace a payout back to the exact rentals that funded it.

---

# 16. Security Architecture

- **PCI Scope Minimization:** Kynetic's backend never receives, transmits, or stores raw card data — all card entry happens inside the provider's hosted checkout (iframe/redirect), meaning Kynetic's PCI DSS scope is the lightest tier (SAQ A), not a full cardholder-data-environment audit.
- **Webhook Signature Validation:** Section 12 — non-negotiable, first check on every webhook.
- **Encryption at Rest:** `host_kyc_records.pan_number_encrypted` and `bank_account_number_encrypted` are encrypted at the application layer (not just relying on disk-level DB encryption) using the same HSM-backed KMS architecture from Security Plan v3, Section 4 — a database dump alone is never sufficient to recover PAN/bank details.
- **RBAC:** `GET /v1/ledger` and `POST /payments/refund` are admin/finance-role-gated only; no developer or host role can ever query raw ledger entries directly, only their own derived summaries (Section 17).
- **Fraud Detection Hooks:** every `orders` creation and every `create_transfer` call passes through the same device-fingerprinting and behavioral-analytics hooks already specified in the Security Architecture (Kynetic_AI_Security_Architecture.md, Pillar 6) — payment fraud and payout fraud are two instances of the same fraud graph, not separate systems.
- **Double-Payment Protection:** `Idempotency-Key` enforcement (Redis-backed, 24h TTL) on `POST /payments/order` prevents a double-tapped "top up" button from creating two orders; the ledger's balanced double-entry design (Section 7) makes any accidental double-credit immediately visible in daily reconciliation even if it somehow slipped past the idempotency layer.
- **Replay Attack Protection:** webhook `provider_event_id` uniqueness (Section 12) + standard request-level replay protection (timestamp + nonce validation) on any signed internal service-to-service financial call.

---

# 17. Dashboard Design

### Admin Dashboard
Revenue (real-time + historical), host earnings outstanding, pending settlements queue, pending payouts queue, refund queue (with one-click approve/deny gated by the Section 18 eligibility check), chargeback queue, invoice search, tax reports (GST collected/payable by period), commission reports (revenue by rule/scope — which commission tiers are actually driving revenue), full financial audit trail (`ledger_entries` browser, read-only, admin/finance role only).

### Customer (Developer) Dashboard
Payment history, invoices (downloadable PDF), current running charges (live-updating via the same metering stream powering billing), past rentals with final cost breakdown, refund status tracker, current usage (GPU utilization tied to cost, so a developer can see "why" their bill is what it is), estimated cost for any currently-running instance projected to its likely stop time.

### Host Dashboard
Current earnings (this cycle, `pending_settlement`), pending earnings (accrued but not yet due for payout per their cycle), available balance, upcoming payout (amount + date), completed payout history (with drill-down to the exact rentals in Section 15's traceability), effective commission rate currently applied to them (transparency — a host should never have to guess what percentage they're being charged), historical revenue trend, payment account status (`payment_provider_accounts.account_status`), KYC status with clear next-step guidance if `kyc_rejected`.

---

# 18. Failure Recovery

| Scenario | Detection | Handling | Recovery |
|---|---|---|---|
| Payment succeeds at provider but webhook never arrives | Ledger reconciliation fails to find a matching `CUSTOMER_PAYMENT` entry for a `payments` row within an expected window | Scheduled reconciliation job polls the provider's order-status API directly as a fallback to webhook delivery | CUSTOMER_PAYMENT ledger entry written retroactively once confirmed; webhook processed normally if it arrives late (idempotent via `provider_event_id`) |
| Refund requested after host already paid out | Refund Validator checks whether the relevant `host_earnings` row is already `settled` | If already settled, refund is issued from `refund_reserve` (a platform-funded buffer), and the host's earnings are *not* automatically clawed back — instead flagged for manual finance review per the host agreement's dispute terms | Prevents clawing back money from a host's bank account, which is operationally and legally fraught; the platform absorbs short-term timing risk by design |
| Chargeback initiated by customer's card issuer | Provider webhook (a new event type, added to Section 12's handled list) | Relevant account ledger balance frozen (extended with ledger-level chargeback entries per Section 7) | Dispute evidence assembled from `billing_sessions`/`usage_records` (proof compute was actually delivered) submitted back to the provider |
| Payout fails permanently (bad bank details) | `ProviderPermanentError` (Section 15) | Host notified immediately with clear resubmission instructions; earnings remain safely in `pending_settlement`, never lost | Host updates bank details → KYC re-verification of the new bank account → payout re-attempted next cycle |
| Commission rule misconfigured (e.g., accidentally set to 0% globally) | Daily reconciliation (Section 7) flags `platform_revenue` growth rate anomaly vs. transaction volume | Alert fires before the next payout cycle executes, giving finance a window to correct the rule before money moves incorrectly | Corrected via a new `commission_rules` row (never edit history) with an `adjustment` ledger entry for any transactions already affected |

---

# 19. MVP Scope

| Category | Included |
|---|---|
| **Must Build** | Direct payment capture via one provider adapter (Razorpay Route, India-first), payment order + webhook handling, per-second metering (existing), commission engine (global rule only, no overrides yet), host_earnings ledger, manual payout trigger (`POST /payouts/create`, admin-initiated — not yet fully scheduled/automated), basic KYC (PAN + bank account, manual approval acceptable pre-scale), core security (signature verification, PCI-minimized checkout, encryption at rest) |
| **Should Build (Fast Follow)** | Automated scheduled payouts (daily/weekly/monthly Celery Beat), Cashfree adapter as a second provider (proves the abstraction actually works, not just theoretical), commission overrides (host-specific, promotional), refund workflow with eligibility validation, admin dashboard (Section 17), UPI support for host payouts |
| **Can Wait** | Postpaid/credit-limit billing for enterprise, coupon/promo code engine, tax-record automation beyond basic GST, host risk-score-driven settlement delay, multi-currency support beyond INR/USD |
| **Future** | Stripe Connect / Adyen / Wise adapters for global host expansion, promotional billing credits as a distinct currency, enterprise-negotiated commission workflows with contract management, automated dispute-evidence assembly for chargebacks |

---

# 20. Engineering Roadmap

### Phase P1 — Payment Collection Foundation
**Objectives:** Direct payment capture via Razorpay adapter, order/payment/webhook tables, signature verification, CUSTOMER_PAYMENT ledger entry.
**DB Migrations:** `orders`, `payments`, `webhook_events`.
**Backend:** `RazorpayRouteAdapter` (order creation + webhook verification only, no transfers yet), `PaymentProviderInterface`.
**Testing:** webhook signature verification unit tests (valid, tampered, replayed).
**Dependencies:** `orders`, `payments`, `v7_ledger_entries`. **Risk:** Medium. **Complexity:** Medium.
**Acceptance:** a real payment capture via Razorpay's test mode correctly writes a CUSTOMER_PAYMENT ledger entry exactly once, even if the webhook is delivered twice.

### Phase P2 — Ledger Foundation
**Objectives:** Double-entry `ledger_entries`, reconciliation job skeleton.
**DB Migrations:** `ledger_entries`.
**Backend:** ledger-writing helper called from every existing money-movement path (payment capture, usage debit, refund, etc.).
**Testing:** assert every test transaction produces balanced debit/credit pairs.
**Dependencies:** P1. **Risk:** Medium. **Complexity:** Medium.
**Acceptance:** the reconciliation identity from Section 7 holds across 1,000 simulated randomized transactions.

### Phase P3 — Host Onboarding & KYC
**Objectives:** Full onboarding state machine (Section 13), `host_kyc_records`, `payment_provider_accounts`.
**Backend:** KYC submission endpoint, Razorpay linked-account creation call, KYC webhook handling.
**Frontend/Host Dashboard:** onboarding wizard, KYC status display.
**Testing:** state-machine transition tests, rejected-KYC resubmission flow.
**Dependencies:** P1. **Risk:** Medium-High (external KYC provider dependency). **Complexity:** High.
**Acceptance:** a test host completes onboarding end-to-end and reaches `active` status with a real (sandbox) linked account created.

### Phase P4 — Commission Engine & Host Earnings
**Objectives:** `commission_rules` (global rule only for MVP), `host_earnings` creation on billing-session close.
**Backend:** `resolve_commission_rate()`, wiring into the existing `finalize_billing` flow (Implementation Plan v5, Phase 28).
**Testing:** verify correct commission split arithmetic against the ledger (Section 7's worked example).
**Dependencies:** P2, P3. **Risk:** Low-Medium. **Complexity:** Medium.
**Acceptance:** a completed rental produces exactly matching `host_earnings.net_amount` + `platform_commission` ledger amounts summing to `final_cost`.

### Phase P5 — Payout Engine
**Objectives:** Manual payout trigger (MVP), then scheduled automation (fast-follow), `payouts`/`payout_line_items`/`settlements`.
**Backend:** `execute_payout` Celery task, idempotent transfer calls, reconciliation job.
**Testing:** simulated provider timeout → retry → eventual success; simulated permanent failure → manual_review escalation.
**Dependencies:** P3, P4. **Risk:** High (real money leaving the platform — the highest-stakes phase in this entire document). **Complexity:** High.
**Acceptance:** a test host with pending earnings receives a real (sandbox) transfer, and a forced provider-error scenario correctly reaches `manual_review` without ever double-paying.

### Phase P6 — Refunds & Failure Recovery
**Objectives:** Refund workflow with eligibility validation, chargeback handling extension, all Section 18 scenarios.
**Testing:** refund-after-host-paid scenario specifically (the trickiest case in Section 18).
**Dependencies:** P1–P5. **Risk:** Medium. **Complexity:** Medium.
**Acceptance:** every row in the Section 18 failure table has a passing integration test.

### Phase P7 — Dashboards & Second Provider
**Objectives:** Admin/Customer/Host dashboards (Section 17), Cashfree adapter as the abstraction-proof second implementation.
**Dependencies:** P1–P6. **Risk:** Low. **Complexity:** Medium.
**Acceptance:** switching a test host's provider from Razorpay to Cashfree requires zero changes to Billing/Commission/Payout Engine code — only a new adapter class and a config entry.

---

# 21. Future Scaling Strategy

- **Multi-provider expansion**: Stripe Connect for hosts outside India, Adyen for broader global card acquiring, Wise for low-fee cross-border payout corridors — all additive per the Section 10 factory pattern, never requiring changes to core billing/commission/ledger logic.
- **Ledger sharding**: as `ledger_entries` volume grows, partition by month — reconciliation jobs move from full-table scans to incremental, partition-aware queries.
- **Payout batching at scale**: once host count reaches a volume where per-host individual Transfer API calls become a bottleneck, move to providers' bulk-transfer/batch-payout endpoints where available, while preserving the same idempotency-key discipline per line item.
- **Tax engine generalization**: today's GST-only tax logic generalizes into a pluggable per-jurisdiction tax-rule table as Kynetic expands beyond India, avoiding a rewrite when the first EU or US enterprise host/customer arrives.
- **Real-time settlement (future, provider-dependent):** as instant-settlement rails (e.g., UPI-linked real-time payout corridors) mature, the Payout Engine's scheduling logic can shorten the default cycle from daily toward near-real-time for hosts opted into it — the architecture already supports this since `payout_cycle` is per-host configuration, not a platform-wide constant.
