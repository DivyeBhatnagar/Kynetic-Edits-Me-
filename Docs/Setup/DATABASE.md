# Kynetic AI — Database Schema & Migration Guide

This document details the relational database schema, ORM model structures, double-entry financial ledgers, per-second metering jobs, host command audit trails, and Alembic migration procedures for **PostgreSQL 15**.

---

## 1. Relational Database Schema Overview

```
┌───────────────────┐       ┌───────────────────┐       ┌───────────────────┐
│       users       │       │       hosts       │       │     listings      │
├───────────────────┤       ├───────────────────┤       ├───────────────────┤
│ id (PK)           │◄──────│ user_id (FK)      │◄──────│ host_id (FK)      │
│ email             │       │ status            │       │ price_per_hour_usd│
│ role              │       │ agent_version     │       │ status            │
│ created_at        │       │ os_type           │       │ created_at        │
└─────────┬─────────┘       └─────────┬─────────┘       └─────────┬─────────┘
          │                           │                           │
          ▼                           ▼                           ▼
┌───────────────────┐       ┌───────────────────┐       ┌───────────────────┐
│      wallets      │       │   host_commands   │       │     instances     │
├───────────────────┤       ├───────────────────┤       ├───────────────────┤
│ user_id (FK, PK)  │       │ id (PK)           │       │ id (PK)           │
│ balance_usd       │       │ host_id (FK)      │◄──────│ developer_id (FK) │
│ balance_inr       │       │ idempotency_key   │       │ listing_id (FK)   │
│ updated_at        │       │ status            │       │ status            │
└─────────┬─────────┘       └───────────────────┘       └─────────┬─────────┘
          │                                                       │
          ▼                                                       ▼
┌───────────────────┐                                   ┌───────────────────┐
│  ledger_entries   │ (Double-Entry Ledger)                 │billing_meter_jobs │
├───────────────────┤                                   ├───────────────────┤
│ transaction_id    │                                   │ id (PK)           │
│ account           │                                   │ instance_id (FK)  │
│ debit / credit    │                                   │ celery_task_id    │
└───────────────────┘                                   │ billed_seconds    │
                                                        └───────────────────┘
```

---

## 2. Primary Database Tables Reference

### Core Platform Tables
- **`users`**: Platform user accounts (`id`, `email`, `hashed_password`, `role['developer'|'host'|'admin']`, `is_active`, `created_at`).
- **`hosts`**: Hardware host nodes (`id`, `user_id`, `status['pending_verification'|'verified'|'listed'|'suspended']`, `os_type`, `agent_version`, `created_at`).
- **`host_heartbeats`**: Real-time heartbeat logs (`id`, `host_id`, `status['idle'|'busy'|'offline']`, `recorded_at`).
- **`listings`**: Active compute listings (`id`, `host_id`, `owner_user_id`, `resource_type`, `price_per_hour_usd`, `price_per_hour_inr`, `status['active'|'paused'|'delisted']`).
- **`instances`**: Instance lifecycle records (`id`, `developer_id`, `listing_id`, `host_id`, `status['pending'|'provisioning'|'running'|'stopping'|'stopped'|'terminated'|'failed']`, `hold_amount`, `price_per_second_usd`, `wireguard_ip`, `billed_seconds`, `started_at`, `stopped_at`, `terminated_at`).
- **`ssh_sessions`**: Ephemeral SSH credentials (`id`, `instance_id`, `public_key`, `private_key_encrypted`, `issued_at`, `revoked_at`).
- **`secure_deletion_receipts`**: Cryptographic volume erasure proofs (`id`, `instance_id`, `method`, `agent_confirmation_hash`, `verified_at`).

### Per-Second Metering & Control Command Audit Tables (Phases 28 & 29)
- **`billing_meter_jobs`**: Active per-second billing task trackers (`id`, `instance_id`, `celery_task_id`, `started_at`, `last_debited_at`, `stopped_at`, `billed_seconds_total`). Migration: `0012_billing_meter_jobs.py`.
- **`host_commands`**: Control-plane command audit log (`id`, `host_id`, `instance_id`, `command_type`, `idempotency_key`, `payload`, `status['pending'|'dispatched'|'completed'|'failed'|'timed_out']`, `response`, `error_message`, `dispatched_at`, `completed_at`). Migration: `0013_host_commands.py`.

### Financial & Audit Ledger Tables (Phases 15 & 16)
- **`ledger_entries`**: Double-entry accounting postings (`id`, `transaction_id`, `account`, `debit`, `credit`, `currency['USD'|'INR']`, `created_at`). Enforces $\sum \text{debit} == \sum \text{credit}$.
- **`chargebacks`**: Payment dispute tracking (`id`, `transaction_id`, `user_id`, `provider['stripe'|'razorpay']`, `status['opened'|'under_review'|'won'|'lost']`, `amount`).
- **`tax_withholdings`**: Statutory tax withholdings (`id`, `user_id`, `payout_id`, `jurisdiction['IN_TDS'|'US_1099']`, `gross_payout`, `tax_rate_pct`, `withheld_amount`, `pan_or_tin`).
- **`audit_logs`**: Append-only administrative and instance lifecycle audit events (`id`, `actor_id`, `action`, `resource_type`, `resource_id`, `extra_data`, `created_at`).

---

## 3. Database Migrations (Alembic)

Migrations are stored in `libs/db_models/migrations/versions/`.

### Migration Sequence
- `0001_initial_users.py`: Users and sessions tables
- `0002_hosts.py`: Hosts and host hardware tables
- `0003_marketplace.py`: Listings and wallets tables
- `0004_instances.py`: Instances and SSH sessions tables
- `0012_billing_meter_jobs.py`: Phase 28 per-second billing meter jobs table
- `0013_host_commands.py`: Phase 29 control-plane command audit log table

### Migration Commands
```bash
cd kynetic-ai

# Apply all pending migrations to database
alembic upgrade head

# Rollback last migration step
alembic downgrade -1
```
