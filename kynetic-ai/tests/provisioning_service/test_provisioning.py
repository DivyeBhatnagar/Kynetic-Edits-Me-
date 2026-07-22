"""
Tests — Provisioning State Machine.

Validates the InstanceRepository state machine logic
(LEGAL_TRANSITIONS and IllegalTransitionError) without a real DB.
"""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from libs.db_models.provisioning_models import InstanceStatus
from services.provisioning_service.repository import (
    IllegalTransitionError,
    InstanceRepository,
    LEGAL_TRANSITIONS,
)


# ── Helpers ───────────────────────────────────────────────────────────────

def make_instance(status: InstanceStatus) -> MagicMock:
    """Returns a mock Instance ORM object."""
    inst = MagicMock()
    inst.id = uuid.uuid4()
    inst.status = status
    inst.started_at = None
    inst.stopped_at = None
    inst.terminated_at = None
    inst.firecracker_vm_id = None
    inst.container_id = None
    inst.wireguard_ip = None
    return inst


async def _transition(from_status: InstanceStatus, to_status: InstanceStatus):
    """Helper: try to transition an instance and return it (or raise)."""
    session = AsyncMock()
    repo = InstanceRepository(session)
    inst = make_instance(from_status)
    with patch.object(repo, "get_by_id", return_value=inst):
        session.flush = AsyncMock()
        return await repo.transition_state(inst.id, to_status)


# ── State machine tests ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pending_to_provisioning():
    inst = await _transition(InstanceStatus.pending, InstanceStatus.provisioning)
    assert inst.status == InstanceStatus.provisioning


@pytest.mark.asyncio
async def test_provisioning_to_running():
    inst = await _transition(InstanceStatus.provisioning, InstanceStatus.running)
    assert inst.status == InstanceStatus.running
    assert inst.started_at is not None


@pytest.mark.asyncio
async def test_running_to_stopping():
    inst = await _transition(InstanceStatus.running, InstanceStatus.stopping)
    assert inst.status == InstanceStatus.stopping
    assert inst.stopped_at is not None


@pytest.mark.asyncio
async def test_running_to_terminated():
    inst = await _transition(InstanceStatus.running, InstanceStatus.terminated)
    assert inst.status == InstanceStatus.terminated
    assert inst.terminated_at is not None


@pytest.mark.asyncio
async def test_illegal_terminated_to_running():
    """Terminated instances cannot be restarted — must raise."""
    with pytest.raises(IllegalTransitionError) as exc:
        await _transition(InstanceStatus.terminated, InstanceStatus.running)
    assert exc.value.current == InstanceStatus.terminated
    assert exc.value.requested == InstanceStatus.running


@pytest.mark.asyncio
async def test_illegal_pending_to_running():
    """Must go through provisioning — cannot skip directly to running."""
    with pytest.raises(IllegalTransitionError):
        await _transition(InstanceStatus.pending, InstanceStatus.running)


@pytest.mark.asyncio
async def test_illegal_stopped_to_provisioning():
    """Stopped instances can only go to running or terminated."""
    with pytest.raises(IllegalTransitionError):
        await _transition(InstanceStatus.stopped, InstanceStatus.provisioning)


def test_legal_transitions_completeness():
    """Every InstanceStatus enum member must have an entry in LEGAL_TRANSITIONS."""
    for status in InstanceStatus:
        assert status in LEGAL_TRANSITIONS, (
            f"InstanceStatus.{status.name} missing from LEGAL_TRANSITIONS"
        )


def test_terminal_states_have_no_transitions():
    """Terminated instances should have no legal next states."""
    assert LEGAL_TRANSITIONS[InstanceStatus.terminated] == set()


# ── SSH key encryption tests ───────────────────────────────────────────────

def test_ssh_key_encrypt_decrypt_roundtrip():
    """
    Encrypt a key, decrypt it, verify the plaintext is identical.
    Uses a test Fernet key (not the production key).
    """
    from cryptography.fernet import Fernet
    from services.provisioning_service.ssh_keys import encrypt_private_key, decrypt_private_key

    test_key = Fernet.generate_key().decode()
    with patch("services.provisioning_service.ssh_keys.settings") as mock_settings:
        mock_settings.ssh_key_fernet_key = test_key

        original = "-----BEGIN OPENSSH PRIVATE KEY-----\nFAKE_KEY_FOR_TESTING\n-----END OPENSSH PRIVATE KEY-----\n"
        encrypted = encrypt_private_key(original)
        assert encrypted != original
        assert "FAKE_KEY" not in encrypted

        decrypted = decrypt_private_key(encrypted)
        assert decrypted == original


def test_generate_keypair_format():
    """Generated public key must be in OpenSSH format."""
    from services.provisioning_service.ssh_keys import generate_keypair
    public_key, private_key_pem = generate_keypair()
    assert public_key.startswith("ssh-rsa "), f"Expected OpenSSH format, got: {public_key[:30]}"
    assert "BEGIN OPENSSH PRIVATE KEY" in private_key_pem


def test_ssh_command_builder():
    """Verify SSH command string is correctly formatted."""
    from services.provisioning_service.ssh_keys import build_ssh_command
    cmd = build_ssh_command(ssh_host="10.42.1.5", ssh_port=22)
    assert "kynetic@10.42.1.5" in cmd
    assert "kynetic_key.pem" in cmd

    cmd_alt = build_ssh_command(ssh_host="relay.kynetic.ai", ssh_port=2222)
    assert "-p 2222" in cmd_alt


# ── WireGuard IP allocation tests ──────────────────────────────────────────

def test_wireguard_ip_deterministic():
    """Same UUID always produces the same WireGuard IP."""
    from services.provisioning_service.wireguard import allocate_wireguard_ip
    iid = uuid.uuid4()
    with patch("services.provisioning_service.wireguard.settings") as ms:
        ms.firecracker_mock = True
        ms.wireguard_subnet = "10.42.0.0/16"
        ip1 = allocate_wireguard_ip(iid)
        ip2 = allocate_wireguard_ip(iid)
    assert ip1 == ip2


def test_wireguard_ip_in_subnet():
    """Allocated IP must be within the configured subnet."""
    import ipaddress
    from services.provisioning_service.wireguard import allocate_wireguard_ip
    iid = uuid.uuid4()
    subnet = "10.42.0.0/16"
    with patch("services.provisioning_service.wireguard.settings") as ms:
        ms.firecracker_mock = True
        ms.wireguard_subnet = subnet
        ip = allocate_wireguard_ip(iid)
    network = ipaddress.IPv4Network(subnet, strict=False)
    assert ipaddress.IPv4Address(ip) in network
