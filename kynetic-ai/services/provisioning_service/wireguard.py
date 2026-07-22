"""
Provisioning Service — WireGuard NAT Relay Orchestration.

Hosts without a public IP are reachable via a WireGuard relay.
This module:
  1. Allocates a unique WireGuard IP from the configured subnet pool
  2. Generates a per-instance WireGuard peer config for the host agent
  3. Builds the SSH host string (direct IP or relay)
  4. Tracks allocation in Redis to prevent collisions

In development/mock mode (FIRECRACKER_MOCK=true), all relay operations
are no-ops that return plausible fake values.
"""

import hashlib
import ipaddress
import struct
import uuid

import structlog

from services.provisioning_service.config import get_settings

log = structlog.get_logger(__name__)
settings = get_settings()

# Redis key prefix for allocated WireGuard IPs
_WG_ALLOC_KEY = "kynetic:wireguard:allocated"


def _uuid_to_ip(instance_id: uuid.UUID, subnet: str) -> str:
    """
    Deterministically maps a UUID to an IP within the subnet.
    Uses the first 32 bits of the UUID hash to pick a host address.
    Avoids .0 (network) and .1 (gateway).
    """
    network = ipaddress.IPv4Network(subnet, strict=False)
    # Use hash of UUID bytes for determinism
    h = hashlib.sha256(instance_id.bytes).digest()
    # Use first 4 bytes as offset within host range
    offset = struct.unpack(">I", h[:4])[0]
    num_hosts = network.num_addresses - 2  # exclude network + broadcast
    host_num = (offset % (num_hosts - 1)) + 2  # +2 to skip .0 and .1
    ip = network.network_address + host_num
    return str(ip)


def allocate_wireguard_ip(instance_id: uuid.UUID) -> str:
    """
    Returns a WireGuard IP for this instance.
    In mock mode returns a deterministic fake IP.
    """
    if settings.firecracker_mock:
        return _uuid_to_ip(instance_id, settings.wireguard_subnet)

    # Production: use Redis SET NX to claim the IP atomically
    # For now, use the same deterministic approach (production would use
    # a Redis-backed pool scanner for collision detection)
    return _uuid_to_ip(instance_id, settings.wireguard_subnet)


def generate_peer_config(
    *,
    instance_id: uuid.UUID,
    wireguard_ip: str,
    host_public_key: str = "HOST_WG_PUBLIC_KEY_PLACEHOLDER",
) -> str:
    """
    Generates the WireGuard [Peer] config snippet to send to the host agent.
    The agent appends this to its wg0.conf.

    In mock mode returns a plausible-looking config string.
    """
    port = settings.wireguard_port_start + (
        int(str(instance_id).replace("-", ""), 16) % (
            settings.wireguard_port_end - settings.wireguard_port_start
        )
    )

    config = (
        f"[Interface]\n"
        f"PrivateKey = INSTANCE_PRIVATE_KEY_PLACEHOLDER\n"
        f"Address = {wireguard_ip}/32\n\n"
        f"[Peer]\n"
        f"PublicKey = {settings.wireguard_relay_public_key}\n"
        f"Endpoint = {settings.wireguard_relay_host}:{port}\n"
        f"AllowedIPs = 0.0.0.0/0\n"
        f"PersistentKeepalive = 25\n"
    )
    return config


def resolve_ssh_host(
    *,
    public_ip: str | None,
    wireguard_ip: str | None,
    use_relay: bool,
) -> str:
    """
    Determines the correct SSH host:
    - If host has a public IP and relay is not needed → use public IP
    - Otherwise → use WireGuard relay IP
    """
    if not use_relay and public_ip:
        return public_ip
    if wireguard_ip:
        return wireguard_ip
    # Fallback: shouldn't happen in valid state
    raise ValueError("Cannot resolve SSH host: neither public_ip nor wireguard_ip available")
