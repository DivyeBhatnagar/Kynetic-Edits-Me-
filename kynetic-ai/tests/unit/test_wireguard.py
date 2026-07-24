"""
Phase 32 Unit Tests — WireGuard NAT Relay & Host Resolution.

Tests:
  - WireGuard IP allocation (deterministic UUID mapping, subnet bounds)
  - Peer configuration snippet generation
  - SSH host resolution rules (direct IP vs relay host)
"""

import uuid
import pytest

from services.provisioning_service.wireguard import (
    _uuid_to_ip,
    allocate_wireguard_ip,
    generate_peer_config,
    resolve_ssh_host,
)


def test_uuid_to_ip_determinism():
    instance_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
    subnet = "10.42.0.0/16"

    ip1 = _uuid_to_ip(instance_id, subnet)
    ip2 = _uuid_to_ip(instance_id, subnet)

    assert ip1 == ip2
    assert ip1.startswith("10.42.")
    assert not ip1.endswith(".0")  # Never network address
    assert not ip1.endswith(".1")  # Never gateway address


def test_allocate_wireguard_ip():
    instance_id = uuid.uuid4()
    ip = allocate_wireguard_ip(instance_id)

    assert isinstance(ip, str)
    assert ip.startswith("10.42.")


def test_generate_peer_config():
    instance_id = uuid.uuid4()
    wg_ip = "10.42.1.50"
    config = generate_peer_config(instance_id=instance_id, wireguard_ip=wg_ip)

    assert "[Interface]" in config
    assert f"Address = {wg_ip}/32" in config
    assert "[Peer]" in config
    assert "AllowedIPs = 0.0.0.0/0" in config


def test_resolve_ssh_host():
    # Direct public IP available and relay not forced
    h1 = resolve_ssh_host(public_ip="203.0.113.5", wireguard_ip="10.42.0.10", use_relay=False)
    assert h1 == "203.0.113.5"

    # Public IP available but relay is forced -> WireGuard IP
    h2 = resolve_ssh_host(public_ip="203.0.113.5", wireguard_ip="10.42.0.10", use_relay=True)
    assert h2 == "10.42.0.10"

    # No public IP -> WireGuard IP
    h3 = resolve_ssh_host(public_ip=None, wireguard_ip="10.42.0.10", use_relay=True)
    assert h3 == "10.42.0.10"

    # Neither public nor WG IP -> ValueError
    with pytest.raises(ValueError):
        resolve_ssh_host(public_ip=None, wireguard_ip=None, use_relay=False)
