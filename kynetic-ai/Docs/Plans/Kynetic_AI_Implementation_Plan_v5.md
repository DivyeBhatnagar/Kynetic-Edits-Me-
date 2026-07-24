# Kynetic AI — Implementation Plan v5
## Closing the Phase 4 Gaps: Business Logic, Billing Events, Host Agent Command Channel & Full Test Coverage

### Purpose of This Document
This plan targets exactly the items flagged as **partial** or **not built** when Harsh's Phase 4 ownership table was cross-checked against the existing docs: Business Logic validation, Billing event integration, Host Agent command channel, Pydantic schemas, Phase-4-specific logging/audit, and the full unit + integration test suites for both Harsh's (application layer) and Divye's (infrastructure layer) sides.

Every phase below is written to be handed directly to an IDE/coding agent: exact file paths, function signatures, working code, and DB/API deltas. Nothing here duplicates what's already built in Phases 1–26 — each phase only adds the missing glue.

---

## Phase 27: Business Logic Validation Layer (Harsh)

**Objective:** Before any instance is created, verify in one place that the developer can afford it, the listing is actually available, the host is online and trustworthy, and the requester has permission — today this logic doesn't exist anywhere, so nothing currently stops an invalid instance request from reaching provisioning.

**File:** `services/provisioning_service/validators.py`

```python
"""
Central validation gate — every instance creation request passes through
validate_instance_request() before any Celery task or Host Agent call fires.
Raises InstanceValidationError with a specific, user-facing reason on failure.
"""
from dataclasses import dataclass
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from libs.db_models.wallet_models import Wallet
from libs.db_models.listing_models import Listing
from libs.db_models.host_models import Host
from libs.db_models.user_models import User


class InstanceValidationError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass
class ValidatedInstanceRequest:
    developer_id: str
    listing_id: str
    host_id: str
    estimated_hourly_cost: Decimal
    currency: str
    hold_amount: Decimal


async def validate_wallet_balance(db: AsyncSession, developer_id: str, hold_amount: Decimal, currency: str) -> Wallet:
    result = await db.execute(select(Wallet).where(Wallet.user_id == developer_id))
    wallet = result.scalar_one_or_none()
    if wallet is None:
        raise InstanceValidationError("WALLET_NOT_FOUND", "No wallet found for this account.")

    balance = wallet.balance_usd if currency == "USD" else wallet.balance_inr
    if balance < hold_amount:
        raise InstanceValidationError(
            "INSUFFICIENT_BALANCE",
            f"Insufficient wallet balance. Required: {hold_amount} {currency}, available: {balance} {currency}.",
        )
    return wallet


async def validate_listing_availability(db: AsyncSession, listing_id: str) -> Listing:
    result = await db.execute(select(Listing).where(Listing.id == listing_id))
    listing = result.scalar_one_or_none()
    if listing is None:
        raise InstanceValidationError("LISTING_NOT_FOUND", "Listing does not exist.")
    if listing.status != "available":
        raise InstanceValidationError("LISTING_UNAVAILABLE", f"Listing is currently '{listing.status}', not available.")
    return listing


async def validate_host_status(db: AsyncSession, host_id: str) -> Host:
    result = await db.execute(select(Host).where(Host.id == host_id))
    host = result.scalar_one_or_none()
    if host is None:
        raise InstanceValidationError("HOST_NOT_FOUND", "Host does not exist.")
    if host.status != "verified":
        raise InstanceValidationError("HOST_NOT_VERIFIED", f"Host status is '{host.status}', not eligible to accept jobs.")

    # Reject hosts that have missed recent heartbeats (stale = likely offline)
    from libs.db_models.host_models import HostHeartbeat
    from sqlalchemy import desc
    hb_result = await db.execute(
        select(HostHeartbeat).where(HostHeartbeat.host_id == host_id).order_by(desc(HostHeartbeat.recorded_at)).limit(1)
    )
    last_heartbeat = hb_result.scalar_one_or_none()
    if last_heartbeat is None or last_heartbeat.status != "idle":
        raise InstanceValidationError("HOST_NOT_IDLE", "Host is not currently idle/available.")
    return host


async def validate_permissions(db: AsyncSession, requester_id: str, developer_id: str) -> None:
    if requester_id != developer_id:
        result = await db.execute(select(User).where(User.id == requester_id))
        user = result.scalar_one_or_none()
        if user is None or user.role not in ("admin",):
            raise InstanceValidationError("PERMISSION_DENIED", "You do not have permission to act on this account.")


async def validate_instance_request(
    db: AsyncSession, requester_id: str, developer_id: str, listing_id: str, requested_hours: Decimal
) -> ValidatedInstanceRequest:
    """Single entrypoint called from POST /instances — orchestrates every check above."""
    await validate_permissions(db, requester_id, developer_id)
    listing = await validate_listing_availability(db, listing_id)
    host = await validate_host_status(db, listing.host_id)

    currency = "INR" if listing.price_per_hour_inr else "USD"
    hourly_price = listing.price_per_hour_inr if currency == "INR" else listing.price_per_hour_usd
    hold_amount = hourly_price * requested_hours

    await validate_wallet_balance(db, developer_id, hold_amount, currency)

    return ValidatedInstanceRequest(
        developer_id=developer_id,
        listing_id=listing_id,
        host_id=host.id,
        estimated_hourly_cost=hourly_price,
        currency=currency,
        hold_amount=hold_amount,
    )
```

**Wire into the API:** `services/provisioning_service/routes/instances.py`

```python
@router.post("/instances", response_model=InstanceResponse, status_code=201)
async def create_instance(
    payload: InstanceCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    validated = await validate_instance_request(
        db, requester_id=current_user.id, developer_id=payload.developer_id,
        listing_id=payload.listing_id, requested_hours=payload.requested_hours,
    )
    instance = await create_instance_record(db, validated)         # Phase 4 (existing)
    await hold_wallet_funds(db, validated.developer_id, validated.hold_amount, validated.currency)  # Phase 28
    provision_instance_task.delay(instance.id)                     # existing Celery task
    return instance
```

**Error handling:** map `InstanceValidationError.code` to HTTP status in a shared exception handler (`services/provisioning_service/exception_handlers.py`) — `WALLET_NOT_FOUND`/`INSUFFICIENT_BALANCE` → 402, `LISTING_UNAVAILABLE`/`HOST_NOT_IDLE` → 409, `PERMISSION_DENIED` → 403.

---

## Phase 28: Billing Event Integration (Harsh + Divye)

**Objective:** Wire the actual event trigger so billing starts the instant an instance becomes `Running` and stops the instant it becomes `Terminated` — today the columns exist (`hold_amount`, `billed_seconds`) but nothing actually flips them at the right moment.

**Design:** Use a lightweight internal event bus over Redis pub/sub so the Provisioning Service (Harsh) and Host Agent status updates (Divye) can both trigger billing state changes without tight coupling.

**File:** `libs/events/bus.py`

```python
import json
import redis.asyncio as redis

REDIS_URL = "redis://redis:6379/2"  # dedicated DB index for events
_client = redis.from_url(REDIS_URL)

INSTANCE_RUNNING = "instance.running"
INSTANCE_TERMINATED = "instance.terminated"
INSTANCE_FAILED = "instance.failed"

async def publish_event(event_type: str, payload: dict) -> None:
    await _client.publish(event_type, json.dumps(payload))

async def subscribe(event_type: str):
    pubsub = _client.pubsub()
    await pubsub.subscribe(event_type)
    async for message in pubsub.listen():
        if message["type"] == "message":
            yield json.loads(message["data"])
```

**Publisher side — Divye's runtime status updater** (`services/provisioning_service/status_sync.py`, called when the Host Agent reports a job actually started/stopped):

```python
from libs.events.bus import publish_event, INSTANCE_RUNNING, INSTANCE_TERMINATED

async def on_host_agent_job_started(instance_id: str, started_at: str):
    await update_instance_status(instance_id, "running", started_at=started_at)  # existing lifecycle update
    await publish_event(INSTANCE_RUNNING, {"instance_id": instance_id, "started_at": started_at})

async def on_host_agent_job_stopped(instance_id: str, stopped_at: str, reason: str):
    await update_instance_status(instance_id, "terminated", stopped_at=stopped_at)
    await publish_event(INSTANCE_TERMINATED, {"instance_id": instance_id, "stopped_at": stopped_at, "reason": reason})
```

**Subscriber side — Billing Service** (`services/wallet_billing_service/event_handlers.py`):

```python
import asyncio
from datetime import datetime, timezone
from libs.events.bus import subscribe, INSTANCE_RUNNING, INSTANCE_TERMINATED

async def handle_instance_running():
    async for event in subscribe(INSTANCE_RUNNING):
        await start_metering(event["instance_id"], billing_start=event["started_at"])
        # schedules a recurring Celery Beat task that debits the wallet every N seconds
        # while status == 'running', using price_per_hour / 3600 as the per-second rate

async def handle_instance_terminated():
    async for event in subscribe(INSTANCE_TERMINATED):
        await stop_metering(event["instance_id"])
        await finalize_billing(event["instance_id"], stopped_at=event["stopped_at"])
        # reconciles: releases unused portion of hold_amount back to wallet,
        # writes final billed_seconds, triggers a wallet_transactions 'debit' record

def start_event_listeners():
    asyncio.create_task(handle_instance_running())
    asyncio.create_task(handle_instance_terminated())
```

**Metering implementation** (`services/wallet_billing_service/metering.py`):

```python
from celery import shared_task
from decimal import Decimal

@shared_task(bind=True)
def debit_running_instance(self, instance_id: str):
    """Celery Beat calls this every 10s for every instance currently 'running'."""
    instance = get_instance_sync(instance_id)
    if instance.status != "running":
        return  # self-cancels once terminated
    rate_per_second = get_hourly_rate(instance) / Decimal(3600)
    debit_amount = rate_per_second * Decimal(10)
    debit_wallet(instance.developer_id, debit_amount, instance.currency, reference_id=instance_id)
    increment_billed_seconds(instance_id, seconds=10)
    if get_wallet_balance(instance.developer_id, instance.currency) <= 0:
        from services.provisioning_service.lifecycle import terminate_instance
        terminate_instance(instance_id, reason="zero_balance_auto_termination")
```

**Database additions:**
- `billing_meter_jobs` (`instance_id`, `celery_task_id`, `started_at`, `last_debited_at`) — tracks the active recurring metering task per instance so it can be cancelled cleanly on termination.

**API additions:** none — this is entirely internal event wiring, no new public endpoints.

---

## Phase 29: Host Agent Command Channel (Divye)

**Objective:** Define the actual command protocol for telling a running Host Agent to launch, stop, or terminate a workload — Phase 2 only built registration and heartbeats; there is currently no mechanism for the control plane to *command* an agent to do something.

**Design:** mTLS-authenticated, idempotent, acknowledgment-based commands over a persistent connection (gRPC bidirectional stream or a WebSocket-over-mTLS channel — gRPC recommended for typed contracts and built-in retry semantics).

**File:** `services/provisioning_service/host_commands.py`

```python
"""
Sends signed, idempotent commands to a specific Host Agent and awaits
acknowledgment. Every command carries a unique idempotency_key so a retried
command (e.g. after a network blip) never double-executes on the agent.
"""
import uuid
import grpc
from dataclasses import dataclass
from proto import host_agent_pb2, host_agent_pb2_grpc  # generated from host_agent.proto

@dataclass
class CommandResult:
    success: bool
    message: str
    idempotency_key: str

async def send_launch_command(host_id: str, instance_id: str, template_id: str | None, image: str) -> CommandResult:
    channel = await get_mtls_channel_for_host(host_id)  # cached, mTLS-authenticated per-host channel
    stub = host_agent_pb2_grpc.HostAgentStub(channel)
    idempotency_key = str(uuid.uuid4())
    request = host_agent_pb2.LaunchRequest(
        instance_id=instance_id, template_id=template_id or "", image=image, idempotency_key=idempotency_key,
    )
    try:
        response = await stub.Launch(request, timeout=30.0)
        return CommandResult(success=response.success, message=response.message, idempotency_key=idempotency_key)
    except grpc.RpcError as e:
        return CommandResult(success=False, message=f"gRPC error: {e.details()}", idempotency_key=idempotency_key)

async def send_stop_command(host_id: str, instance_id: str) -> CommandResult:
    ...  # same pattern, stub.Stop(...)

async def send_terminate_command(host_id: str, instance_id: str) -> CommandResult:
    ...  # same pattern, stub.Terminate(...) — also triggers secure deletion (existing Phase 4 module)
```

**Proto contract:** `proto/host_agent.proto`

```protobuf
syntax = "proto3";

service HostAgent {
  rpc Launch (LaunchRequest) returns (CommandResponse);
  rpc Stop (StopRequest) returns (CommandResponse);
  rpc Terminate (TerminateRequest) returns (CommandResponse);
  rpc StreamStatus (StatusRequest) returns (stream StatusUpdate);
}

message LaunchRequest {
  string instance_id = 1;
  string template_id = 2;
  string image = 3;
  string idempotency_key = 4;
}

message CommandResponse {
  bool success = 1;
  string message = 2;
}

message StatusUpdate {
  string instance_id = 1;
  string status = 2;      // launching | running | stopped | failed
  string timestamp = 3;
}
```

**Agent-side listener:** `host_agent/command_listener.py`

```python
"""
Runs inside the Host Agent binary. Receives commands, deduplicates by
idempotency_key (in-memory LRU + on-disk log for restart-safety), and
executes against the local Firecracker/Docker control engine.
"""
import grpc.aio
from proto import host_agent_pb2, host_agent_pb2_grpc
from host_agent.provisioning_engine import launch_workload, stop_workload, terminate_workload
from host_agent.idempotency_store import already_processed, mark_processed

class HostAgentServicer(host_agent_pb2_grpc.HostAgentServicer):
    async def Launch(self, request, context):
        if already_processed(request.idempotency_key):
            return host_agent_pb2.CommandResponse(success=True, message="Already processed (idempotent replay)")
        try:
            await launch_workload(request.instance_id, request.template_id, request.image)
            mark_processed(request.idempotency_key)
            await notify_control_plane_job_started(request.instance_id)  # calls Phase 28's status_sync
            return host_agent_pb2.CommandResponse(success=True, message="Launched")
        except Exception as e:
            return host_agent_pb2.CommandResponse(success=False, message=str(e))

    async def Stop(self, request, context):
        await stop_workload(request.instance_id)
        return host_agent_pb2.CommandResponse(success=True, message="Stopped")

    async def Terminate(self, request, context):
        await terminate_workload(request.instance_id)  # includes secure deletion (Phase 4 existing)
        await notify_control_plane_job_stopped(request.instance_id, reason="terminated_by_command")
        return host_agent_pb2.CommandResponse(success=True, message="Terminated")
```

**Database additions:**
- `host_commands` (`id`, `host_id`, `instance_id`, `command_type[launch|stop|terminate]`, `idempotency_key`, `status[sent|acked|failed|timed_out]`, `sent_at`, `acked_at`) — audit trail of every command issued, used for debugging stuck provisioning.

**Retry/timeout policy:** if a command times out (30s default) or the host disconnects mid-command, the Provisioning Service Celery task retries up to 3 times with exponential backoff, then marks the instance `failed` and refunds any held wallet balance (calls back into Phase 28's `finalize_billing`).

---

## Phase 30: Pydantic Schema Layer (Harsh)

**Objective:** Formalize request/response validation — currently only implied, never itemized as its own deliverable, which means it's easy to accidentally skip.

**File:** `services/provisioning_service/schemas.py`

```python
from pydantic import BaseModel, Field, field_validator
from decimal import Decimal
from datetime import datetime
from enum import Enum


class InstanceStatus(str, Enum):
    pending = "pending"
    provisioning = "provisioning"
    running = "running"
    stopping = "stopping"
    terminated = "terminated"
    failed = "failed"


class InstanceCreateRequest(BaseModel):
    developer_id: str
    listing_id: str
    template_id: str | None = None
    requested_hours: Decimal = Field(gt=0, le=720)  # sanity cap: max 30 days per request

    @field_validator("requested_hours")
    @classmethod
    def round_to_hour_precision(cls, v: Decimal) -> Decimal:
        return v.quantize(Decimal("0.01"))


class InstanceResponse(BaseModel):
    id: str
    developer_id: str
    listing_id: str
    host_id: str
    status: InstanceStatus
    hold_amount: Decimal
    currency: str
    billed_seconds: int
    started_at: datetime | None
    stopped_at: datetime | None

    class Config:
        from_attributes = True


class InstanceConnectionResponse(BaseModel):
    instance_id: str
    ssh_command: str | None
    web_ui_url: str | None
    expires_at: datetime


class InstanceActionResponse(BaseModel):
    instance_id: str
    status: InstanceStatus
    message: str
```

Apply the same pattern to every Phase 4 endpoint (`start`, `stop`, `terminate`) — each gets an explicit request/response schema rather than relying on implicit dict returns.

---

## Phase 31: Phase-4-Specific Audit & Diagnostics (Harsh + Divye)

**Objective:** Phase 1 gave you global `structlog` correlation IDs; Plan 2 Phase 13 gave you platform-wide observability. Neither itemizes what's specific to instance lifecycle events — this closes that gap.

**File:** `services/provisioning_service/audit.py`

```python
import structlog
from libs.db_models.audit_models import AuditLog

logger = structlog.get_logger("provisioning")

async def log_instance_event(db, actor_id: str, instance_id: str, action: str, metadata: dict):
    logger.info("instance_event", instance_id=instance_id, action=action, actor_id=actor_id, **metadata)
    await db.execute(
        AuditLog.__table__.insert().values(
            actor_id=actor_id, action=action, resource_type="instance", resource_id=instance_id, metadata=metadata,
        )
    )
```

Call this at every state transition (`create`, `start`, `stop`, `terminate`, `failed`) and at every validation rejection from Phase 27 — a rejected `INSUFFICIENT_BALANCE` attempt is itself a security-relevant signal (Plan 2's fraud detection can later mine this).

**Provisioning diagnostics (Divye's side):** `host_agent/diagnostics.py` — captures provisioning duration, Firecracker boot time, image pull time, and failure stack traces per job, shipped to the centralized log store (Plan 2, Phase 13) tagged by `instance_id` for correlation with the audit log above.

---

## Phase 32: Unit Test Suite

**Objective:** Zero test coverage currently exists anywhere in the codebase. This phase is the single largest genuine gap and should not be deprioritized under launch pressure.

### Harsh's side — `tests/unit/`

**`tests/unit/test_validators.py`**
```python
import pytest
from decimal import Decimal
from services.provisioning_service.validators import validate_instance_request, InstanceValidationError

@pytest.mark.asyncio
async def test_rejects_insufficient_balance(db_session, seeded_wallet_zero_balance, seeded_available_listing):
    with pytest.raises(InstanceValidationError) as exc:
        await validate_instance_request(
            db_session, requester_id="user_1", developer_id="user_1",
            listing_id=seeded_available_listing.id, requested_hours=Decimal("2"),
        )
    assert exc.value.code == "INSUFFICIENT_BALANCE"

@pytest.mark.asyncio
async def test_rejects_unavailable_listing(db_session, seeded_wallet_funded, seeded_rented_listing):
    with pytest.raises(InstanceValidationError) as exc:
        await validate_instance_request(
            db_session, requester_id="user_1", developer_id="user_1",
            listing_id=seeded_rented_listing.id, requested_hours=Decimal("1"),
        )
    assert exc.value.code == "LISTING_UNAVAILABLE"

@pytest.mark.asyncio
async def test_rejects_offline_host(db_session, seeded_wallet_funded, seeded_listing_offline_host):
    with pytest.raises(InstanceValidationError) as exc:
        await validate_instance_request(
            db_session, requester_id="user_1", developer_id="user_1",
            listing_id=seeded_listing_offline_host.id, requested_hours=Decimal("1"),
        )
    assert exc.value.code == "HOST_NOT_IDLE"

@pytest.mark.asyncio
async def test_rejects_permission_mismatch(db_session, seeded_wallet_funded, seeded_available_listing):
    with pytest.raises(InstanceValidationError) as exc:
        await validate_instance_request(
            db_session, requester_id="user_attacker", developer_id="user_victim",
            listing_id=seeded_available_listing.id, requested_hours=Decimal("1"),
        )
    assert exc.value.code == "PERMISSION_DENIED"

@pytest.mark.asyncio
async def test_accepts_valid_request(db_session, seeded_wallet_funded, seeded_available_listing):
    result = await validate_instance_request(
        db_session, requester_id="user_1", developer_id="user_1",
        listing_id=seeded_available_listing.id, requested_hours=Decimal("2"),
    )
    assert result.hold_amount > 0
```

**`tests/unit/test_lifecycle_state_machine.py`** — assert every legal transition succeeds (`pending→provisioning→running→stopping→terminated`) and every illegal one raises (e.g. `terminated→running` must fail).

**`tests/unit/test_billing_integration.py`** — mock `publish_event`/`subscribe` (Phase 28), assert `start_metering` fires exactly once on `INSTANCE_RUNNING` and `finalize_billing` fires exactly once on `INSTANCE_TERMINATED`, and that a zero-balance mid-run triggers `terminate_instance` via `debit_running_instance`.

**`tests/unit/test_instances_api.py`** — FastAPI `TestClient`/`httpx.AsyncClient` tests for every endpoint: 201 on valid create, 402 on insufficient balance, 403 on permission mismatch, 404 on unknown instance ID, correct schema shape on every response (validated against Phase 30 schemas).

### Divye's side — `tests/unit/`

**`tests/unit/test_provisioning_engine.py`** — mock Firecracker/Docker calls, assert `launch_workload` calls the correct isolation setup (VFIO passthrough config, ephemeral volume creation) in the right order, and that a launch failure correctly propagates to `CommandResponse(success=False, ...)`.

**`tests/unit/test_ssh_management.py`** — assert keys are generated fresh per session, never reused, and `revoked_at` is set correctly on termination.

**`tests/unit/test_wireguard.py`** — assert tunnel creation/teardown is idempotent (creating a tunnel for an already-tunneled instance doesn't duplicate config), and teardown actually removes the interface.

**`tests/unit/test_ephemeral_storage.py`** — assert `create_ephemeral_encrypted_volume` produces a fresh key every call, and `secure_destroy_volume` is called exactly once per termination and cannot be skipped even on an error path (test via a forced exception mid-teardown, assert cleanup still ran via `finally`).

**`tests/unit/test_host_commands.py`** — assert `send_launch_command` retries on `grpc.RpcError`, respects the 30s timeout, and never sends two different idempotency keys for the same logical retry.

**Shared fixture file:** `tests/conftest.py` — seeded wallets, listings, hosts, and a mock Host Agent gRPC server (`grpc.aio.server()` with a stub `HostAgentServicer` returning canned responses) so Harsh's tests never require real infrastructure.

**CI gate:** add to `services/provisioning_service` and `host_agent` CI jobs — fail the build if coverage on `validators.py`, `metering.py`, `host_commands.py`, and `lifecycle.py` drops below 85%.

---

## Phase 33: Integration Test Suite

**Objective:** Prove the full request → validation → provisioning → billing → termination chain actually works end-to-end against a real (staging) Celery worker and a real (containerized, not mocked) Host Agent — unit tests alone don't catch wiring bugs between services.

**File:** `tests/integration/test_instance_lifecycle_e2e.py`

```python
"""
Runs against docker-compose.staging.yml: real Postgres, real Redis, real
Celery worker, and a lightweight containerized Host Agent stub that
implements the gRPC contract against a fake local 'GPU' (no real hardware
required for CI — Divye should provide a `host_agent --simulate-gpu` flag).
"""
import pytest
import httpx
import asyncio

@pytest.mark.integration
async def test_full_instance_lifecycle(staging_client: httpx.AsyncClient, funded_developer_token, available_listing_id):
    # 1. Create instance
    resp = await staging_client.post(
        "/instances",
        json={"developer_id": "dev_1", "listing_id": available_listing_id, "requested_hours": "1"},
        headers={"Authorization": f"Bearer {funded_developer_token}"},
    )
    assert resp.status_code == 201
    instance_id = resp.json()["id"]
    assert resp.json()["status"] == "pending"

    # 2. Poll until the real Celery task + Host Agent command channel bring it to 'running'
    for _ in range(30):
        status_resp = await staging_client.get(f"/instances/{instance_id}")
        if status_resp.json()["status"] == "running":
            break
        await asyncio.sleep(1)
    assert status_resp.json()["status"] == "running"

    # 3. Verify billing actually started — hold_amount debited incrementally
    initial_balance = await get_wallet_balance_via_api(staging_client, "dev_1")
    await asyncio.sleep(15)
    later_balance = await get_wallet_balance_via_api(staging_client, "dev_1")
    assert later_balance < initial_balance, "Metering did not debit the wallet during a running instance"

    # 4. Verify connection details are real and usable
    conn_resp = await staging_client.get(f"/instances/{instance_id}/connection")
    assert conn_resp.status_code == 200
    assert conn_resp.json()["ssh_command"] is not None

    # 5. Terminate and verify full cleanup
    term_resp = await staging_client.post(f"/instances/{instance_id}/terminate")
    assert term_resp.status_code == 200
    for _ in range(15):
        status_resp = await staging_client.get(f"/instances/{instance_id}")
        if status_resp.json()["status"] == "terminated":
            break
        await asyncio.sleep(1)
    assert status_resp.json()["status"] == "terminated"

    # 6. Verify billing stopped (no further debits after termination)
    post_term_balance = await get_wallet_balance_via_api(staging_client, "dev_1")
    await asyncio.sleep(12)
    balance_after_wait = await get_wallet_balance_via_api(staging_client, "dev_1")
    assert post_term_balance == balance_after_wait, "Billing continued debiting after termination"

    # 7. Verify secure deletion receipt was generated
    receipt = await get_deletion_receipt_via_db(instance_id)
    assert receipt is not None
    assert receipt.method in ("luks_erase", "cryptsetup_erase")
```

**Additional integration tests to include:**
- `test_insufficient_balance_never_reaches_host_agent.py` — assert a rejected-at-validation request never triggers a single Host Agent gRPC call (spy/mock on the channel, assert zero invocations).
- `test_host_agent_disconnect_mid_provisioning.py` — kill the staging Host Agent container mid-launch, assert the instance correctly transitions to `failed`, wallet hold is refunded (Phase 28's `finalize_billing` refund path), and a `host_commands` row shows `status=timed_out`.
- `test_zero_balance_auto_termination.py` — fund a wallet with exactly 12 seconds' worth of runtime, assert the instance is auto-terminated by `debit_running_instance` within one metering interval of hitting zero.
- `test_idempotent_launch_retry.py` — send the same `idempotency_key` twice to the Host Agent stub, assert the workload is only launched once.

**CI Integration:** runs in a separate CI stage (`integration-tests`) gated behind unit tests passing, using `docker-compose.staging.yml`; not run on every commit (too slow) but required to pass before any merge to `main`.

---

## Summary — What Ships From This Plan

| Phase | Closes Gap | Owner |
|---|---|---|
| 27 | Business Logic validation (wallet/listing/host/permissions) | Harsh |
| 28 | Billing event integration (start/stop metering wiring) | Harsh + Divye |
| 29 | Host Agent command channel (launch/stop/terminate protocol) | Divye |
| 30 | Pydantic request/response schemas | Harsh |
| 31 | Phase-4-specific audit logging & provisioning diagnostics | Harsh + Divye |
| 32 | Full unit test suite, both sides, 85% coverage gate | Harsh + Divye |
| 33 | Full integration test suite, real staging environment | Harsh + Divye |

Once Phases 27–33 are merged, every item flagged as "partial" or "not built" in the Phase 4 ownership review is closed — Phase 4 becomes genuinely production-ready, not just architecturally documented.
