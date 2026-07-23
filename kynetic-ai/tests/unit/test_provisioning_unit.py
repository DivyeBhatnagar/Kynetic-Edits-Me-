"""
Phase 14 — Provisioning & Lifecycle Unit Tests

Tests:
  - Instance status state machine transition rules
  - Invalid state transition prevention
  - SSH key Fernet encryption/decryption helper
"""

import enum
import pytest
from cryptography.fernet import Fernet


class InstanceStatus(str, enum.Enum):
    pending      = "pending"
    provisioning = "provisioning"
    running      = "running"
    stopping     = "stopping"
    terminated   = "terminated"
    failed       = "failed"


VALID_TRANSITIONS = {
    InstanceStatus.pending: {InstanceStatus.provisioning, InstanceStatus.failed},
    InstanceStatus.provisioning: {InstanceStatus.running, InstanceStatus.failed},
    InstanceStatus.running: {InstanceStatus.stopping, InstanceStatus.failed},
    InstanceStatus.stopping: {InstanceStatus.terminated, InstanceStatus.failed},
    InstanceStatus.terminated: set(),
    InstanceStatus.failed: set(),
}


def transition_instance_status(current_status: InstanceStatus, next_status: InstanceStatus) -> InstanceStatus:
    """Validate and execute instance state machine transition."""
    allowed = VALID_TRANSITIONS.get(current_status, set())
    if next_status not in allowed:
        raise ValueError(
            f"Invalid instance status transition: {current_status.value} -> {next_status.value}"
        )
    return next_status


def encrypt_ssh_private_key(private_key: str, fernet_key: str) -> str:
    f = Fernet(fernet_key.encode() if isinstance(fernet_key, str) else fernet_key)
    return f.encrypt(private_key.encode()).decode()


def decrypt_ssh_private_key(token: str, fernet_key: str) -> str:
    f = Fernet(fernet_key.encode() if isinstance(fernet_key, str) else fernet_key)
    return f.decrypt(token.encode()).decode()


class TestProvisioningUnitLogic:
    """Unit tests for instance provisioning state machine and key security."""

    def test_valid_state_machine_flow(self):
        status = InstanceStatus.pending
        status = transition_instance_status(status, InstanceStatus.provisioning)
        assert status == InstanceStatus.provisioning

        status = transition_instance_status(status, InstanceStatus.running)
        assert status == InstanceStatus.running

        status = transition_instance_status(status, InstanceStatus.stopping)
        assert status == InstanceStatus.stopping

        status = transition_instance_status(status, InstanceStatus.terminated)
        assert status == InstanceStatus.terminated

    def test_invalid_state_transition_throws_error(self):
        # Cannot jump from pending directly to running
        with pytest.raises(ValueError):
            transition_instance_status(InstanceStatus.pending, InstanceStatus.running)

        # Cannot restart a terminated instance
        with pytest.raises(ValueError):
            transition_instance_status(InstanceStatus.terminated, InstanceStatus.running)

    def test_fernet_ssh_key_encryption_decryption(self):
        key = Fernet.generate_key().decode()
        dummy_ssh_private_key = "-----BEGIN OPENSSH PRIVATE KEY-----\ntest_key\n-----END OPENSSH PRIVATE KEY-----"

        encrypted = encrypt_ssh_private_key(dummy_ssh_private_key, key)
        assert encrypted != dummy_ssh_private_key

        decrypted = decrypt_ssh_private_key(encrypted, key)
        assert decrypted == dummy_ssh_private_key
