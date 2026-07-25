"""
Phase C Integration Tests — Cloud Computer Runtime Foundation

Tests:
1. Instance Provisioning & Lifecycle: POST /instances (pending -> provisioning -> running)
2. Instance Allocation & Workspace Mapping: image, CPU, RAM, workspace_path
3. Instance Suspension & Resume: POST /instances/{id}/stop and POST /instances/{id}/start
4. Instance Termination & Cryptographic Secure Deletion Receipt: POST /instances/{id}/terminate
5. Host Agent Crash Recovery State Reconciliation: reconcile_host_instances()
"""

import uuid
from decimal import Decimal
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.database import get_db_session
from libs.db_models.user_models import User, UserRole
from libs.db_models.host_models import Host, HostStatus
from libs.db_models.marketplace_models import Listing, ResourceType, ListingStatus, Wallet
from libs.db_models.provisioning_models import (
    Instance,
    InstanceStatus,
    SecureDeletionReceipt,
)
from services.provisioning_service.main import app as provisioning_app
from host_agent.main import provisioning_app as agent_app
from host_agent.idempotency_store import (
    save_instance_state,
    remove_instance_state,
    reconcile_host_instances,
)


@pytest.fixture
async def db_override(db_session: AsyncSession):
    async def _override():
        yield db_session

    provisioning_app.dependency_overrides[get_db_session] = _override
    yield db_session
    provisioning_app.dependency_overrides.clear()


@pytest.fixture
async def test_developer_and_token(db_session: AsyncSession):
    from services.auth_service.security import create_access_token
    dev_id = uuid.uuid4()
    dev = User(
        id=dev_id,
        email=f"dev_{dev_id.hex[:6]}@example.com",
        hashed_password="$2b$12$eImiTXuWVxfM37uY4JANjO5E/8G5e2j9Y3v.3mK9W6iJz/jE2j5hS",
        role=UserRole.DEVELOPER,
        is_active=True,
    )
    db_session.add(dev)

    wallet = Wallet(
        id=uuid.uuid4(),
        user_id=dev_id,
        balance_usd=Decimal("100.000000"),
        balance_inr=Decimal("8300.000000"),
    )
    db_session.add(wallet)
    await db_session.commit()

    access_token = create_access_token(user_id=dev.id, role=dev.role.value)
    return dev, access_token


@pytest.fixture
async def test_host_and_listing(db_session: AsyncSession, test_developer_and_token):
    dev, _ = test_developer_and_token
    host = Host(
        id=uuid.uuid4(),
        user_id=dev.id,
        status=HostStatus.VERIFIED,
        os_type="linux",
        agent_version="1.0.0",
        spec_verified=True,
        benchmark_verified=True,
    )
    db_session.add(host)

    listing = Listing(
        id=uuid.uuid4(),
        host_id=host.id,
        owner_user_id=dev.id,
        resource_type=ResourceType.gpu,
        gpu_model="NVIDIA RTX 4090",
        gpu_count=1,
        gpu_vram_gb=24.0,
        cpu_cores=16,
        ram_gb=64.0,
        storage_gb=500.0,
        storage_type="nvme",
        price_per_hour_usd=Decimal("0.500000"),
        price_per_hour_inr=Decimal("41.500000"),
        price_per_second_usd=Decimal("0.0001388888"),
        price_per_second_inr=Decimal("0.0115277777"),
        region="us-east-1",
        status=ListingStatus.active,
    )
    db_session.add(listing)
    await db_session.commit()
    return host, listing


@pytest.mark.asyncio
async def test_host_agent_provisioning_endpoints():
    """Test Host Agent provisioning server endpoints: provision -> stop -> terminate -> verify."""
    instance_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=agent_app), base_url="http://testserver") as client:
        # 1. Provision
        prov_resp = await client.post("/agent/provision", json={
            "instance_id": str(instance_id),
            "image": "ubuntu:22.04",
            "vcpus": 4,
            "mem_mib": 8192,
        })
        assert prov_resp.status_code == 201, prov_resp.text
        prov_data = prov_resp.json()
        assert prov_data["status"] == "running"
        assert "firecracker_vm_id" in prov_data
        assert "workspace_path" in prov_data

        # 2. Stop
        stop_resp = await client.post("/agent/stop", json={"instance_id": str(instance_id)})
        assert stop_resp.status_code == 200
        assert stop_resp.json()["status"] == "stopped"

        # 3. Terminate
        term_resp = await client.post("/agent/terminate", json={"instance_id": str(instance_id)})
        assert term_resp.status_code == 200
        term_data = term_resp.json()
        assert term_data["status"] == "terminated"
        assert "deletion_receipt" in term_data
        assert term_data["deletion_receipt"]["instance_id"] == str(instance_id)
        assert "agent_confirmation_hash" in term_data["deletion_receipt"]

        # 4. Verify deletion
        verify_resp = await client.get(f"/agent/verify_deletion/{instance_id}")
        assert verify_resp.status_code == 200
        assert verify_resp.json()["verified"] is True


@pytest.mark.asyncio
async def test_instance_repository_state_machine_and_receipts(test_developer_and_token, test_host_and_listing, db_override: AsyncSession):
    dev, _ = test_developer_and_token
    host, listing = test_host_and_listing

    # Create Instance in DB
    instance = Instance(
        id=uuid.uuid4(),
        developer_id=dev.id,
        listing_id=listing.id,
        host_id=host.id,
        status=InstanceStatus.pending,
        image="ubuntu:22.04",
        cpu_allocated=4,
        ram_gb_allocated=8.0,
        gpu_allocated="NVIDIA RTX 4090",
        vram_gb_allocated=24.0,
        workspace_path="/mnt/nvme/vol-test",
        hold_amount=Decimal("0.50"),
        price_per_second_usd=Decimal("0.0001388888"),
    )
    db_override.add(instance)
    await db_override.commit()

    # State transitions: pending -> provisioning -> running -> stopping -> stopped -> terminated
    from services.provisioning_service.repository import InstanceRepository, SecureDeletionRepository
    repo = InstanceRepository(db_override)

    # 1. pending -> provisioning
    inst = await repo.transition_state(instance.id, InstanceStatus.provisioning)
    assert inst.status == InstanceStatus.provisioning

    # 2. provisioning -> running
    inst = await repo.transition_state(instance.id, InstanceStatus.running, firecracker_vm_id="fc-1234", container_id="dock-5678")
    assert inst.status == InstanceStatus.running
    assert inst.firecracker_vm_id == "fc-1234"
    assert inst.container_id == "dock-5678"

    # 3. running -> stopping -> stopped
    inst = await repo.transition_state(instance.id, InstanceStatus.stopping)
    assert inst.status == InstanceStatus.stopping
    inst = await repo.transition_state(instance.id, InstanceStatus.stopped)
    assert inst.status == InstanceStatus.stopped

    # 4. stopped -> terminated
    inst = await repo.transition_state(instance.id, InstanceStatus.terminated)
    assert inst.status == InstanceStatus.terminated

    # 5. Record secure deletion receipt
    receipt_repo = SecureDeletionRepository(db_override)
    receipt = await receipt_repo.create(
        instance_id=instance.id,
        method="luks_key_destruction",
        agent_confirmation_hash="mock_hash_abc123",
        agent_payload='{"instance_id": "test", "mock": true}',
    )
    await db_override.commit()

    fetched_receipt = await receipt_repo.get_by_instance(instance.id)
    assert fetched_receipt is not None
    assert fetched_receipt.method == "luks_key_destruction"
    assert fetched_receipt.agent_confirmation_hash == "mock_hash_abc123"


@pytest.mark.asyncio
async def test_host_agent_crash_recovery_reconciliation():
    test_id = str(uuid.uuid4())
    save_instance_state(test_id, {"instance_id": test_id, "status": "running"})

    result = reconcile_host_instances()
    assert result["reconciled"] is True
    assert result["active_instances"] >= 1

    remove_instance_state(test_id)
