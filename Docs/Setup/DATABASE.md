# Kynetic AI — Database Schema & Migration Guide

This document details the relational database schema, ORM model structures, double-entry financial ledgers, and Alembic migration procedures for **PostgreSQL 15**.

---

## 1. Relational Database Schema Overview

```
┌───────────────────┐       ┌───────────────────┐       ┌───────────────────┐
│       users       │       │    host_nodes     │       │     listings      │
├───────────────────┤       ├───────────────────┤       ├───────────────────┤
│ id (PK)           │◄──────│ host_user_id (FK) │◄──────│ host_node_id (FK) │
│ email             │       │ gpu_model         │       │ hourly_price_usd  │
│ role              │       │ reputation_score  │       │ is_active         │
│ created_at        │       │ security_tier     │       │ created_at        │
└─────────┬─────────┘       └───────────────────┘       └─────────┬─────────┘
          │                                                       │
          ▼                                                       ▼
┌───────────────────┐                                   ┌───────────────────┐
│      wallets      │                                   │     rentals       │
├───────────────────┤                                   ├───────────────────┤
│ user_id (FK, PK)  │                                   │ id (PK)           │
│ balance_usd       │                                   │ developer_id (FK) │
│ balance_inr       │                                   │ listing_id (FK)   │
│ updated_at        │                                   │ status            │
└─────────┬─────────┘                                   └───────────────────┘
          │
          ▼
┌───────────────────┐
│  ledger_entries   │  (Double-Entry Accounting)
├───────────────────┤
│ transaction_id    │
│ account           │  (e.g., 'assets:cash', 'liabilities:wallet:user_123', 'revenue:platform_fee')
│ debit             │
│ credit            │
│ currency          │
└───────────────────┘
```

---

## 2. Primary Database Tables Reference

### Core Platform Tables
- **`users`**: Platform user accounts (`id`, `email`, `hashed_password`, `full_name`, `role['developer'|'host'|'admin']`, `is_active`, `created_at`).
- **`host_nodes`**: Hardware host node telemetry (`id`, `host_user_id`, `gpu_model`, `gpu_count`, `vram_gb`, `cpu_cores`, `ram_gb`, `reputation_score`, `security_tier['confidential_tier'|'standard_tier']`, `last_heartbeat`).
- **`listings`**: Active compute availability listings (`id`, `host_node_id`, `hourly_price_usd`, `hourly_price_inr`, `is_active`, `created_at`).
- **`rentals`**: Workload rental sessions (`id`, `developer_id`, `listing_id`, `status['provisioning'|'running'|'stopping'|'terminated']`, `started_at`, `ended_at`, `total_cost_usd`).

### Financial & Audit Ledger Tables (Phases 15 & 16)
- **`ledger_entries`**: Double-entry accounting postings (`id`, `transaction_id`, `account`, `debit`, `credit`, `currency['USD'|'INR']`, `created_at`). Enforces $\sum \text{debit} == \sum \text{credit}$.
- **`chargebacks`**: Payment dispute tracking (`id`, `transaction_id`, `user_id`, `provider['stripe'|'razorpay']`, `status['opened'|'under_review'|'won'|'lost']`, `amount`).
- **`tax_withholdings`**: Statutory tax withholdings (`id`, `user_id`, `payout_id`, `jurisdiction['IN_TDS'|'US_1099']`, `gross_payout`, `tax_rate_pct`, `withheld_amount`, `pan_or_tin`).
- **`ticket_activity_logs`**: Support ticket activity logs (`id`, `ticket_id`, `actor_id`, `action`, `notes`, `created_at`).
- **`fraud_review_items`**: Fraud and trust queue items (`id`, `user_id`, `risk_score`, `reasons`, `status['pending'|'approved'|'rejected']`).

---

## 3. Database Migrations (Alembic)

Migrations are stored in `libs/db_models/alembic/versions/`.

### Migration Commands
```bash
cd kynetic-ai

# Apply all pending migrations to database
alembic upgrade head

# Rollback last migration step
alembic downgrade -1

# Generate a new auto-detected migration script
alembic revision --autogenerate -m "Add security v5 attestation columns"
```
