"""
Unit test suite for Part 4 (Media-Aware Storage Sanitization & LUKS2 Encryption).
"""

import json
import uuid

import pytest

from host_agent.volume_manager import VolumeManager


def test_volume_manager_luks2_lifecycle():
    """Verify VolumeManager LUKS2 allocation and in-memory key destruction upon shred."""
    instance_id = uuid.uuid4()
    vm = VolumeManager(instance_id)

    assert vm._key_bytes is not None
    assert len(vm._key_bytes) == 64

    # Allocate
    dev_path = vm.allocate(size_gb=10)
    assert "mock-vol-" in dev_path

    # Shred
    shred_result = vm.shred()
    assert shred_result["method"] == "luks2_key_destruction_media_aware_sanitize"
    assert "confirmation_hash" in shred_result
    assert len(shred_result["confirmation_hash"]) == 64

    payload = json.loads(shred_result["payload"])
    assert payload["instance_id"] == str(instance_id)
    assert payload["luks_version"] == "LUKS2"
    assert payload["mock"] is True

    # Confirm in-memory key bytes cleared
    assert vm._key_bytes is None
