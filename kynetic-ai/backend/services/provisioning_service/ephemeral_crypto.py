"""
Phase 22 — Ephemeral LUKS Storage & Instant Cryptographic Shredding
Creates per-job LUKS2 encrypted storage partitions with in-memory 512-bit master keys.
On job teardown, performs instant key erasure and disk block wiping.
"""

import secrets
import subprocess


def create_ephemeral_luks_partition(device_node: str, volume_label: str) -> bytes:
    """
    Format device_node as LUKS2 with a random 512-bit key held strictly in memory.
    """
    master_key = secrets.token_bytes(64)  # 512-bit key

    # 1. Format partition
    subprocess.run(
        ["cryptsetup", "luksFormat", "--type", "luks2", "--cipher", "aes-xts-plain64", "--key-size", "512", "--key-file", "-", device_node],
        input=master_key,
        check=True,
    )

    # 2. Open mapped volume
    subprocess.run(
        ["cryptsetup", "open", "--key-file", "-", device_node, volume_label],
        input=master_key,
        check=True,
    )

    return master_key


def destroy_luks_partition_permanently(device_node: str, volume_label: str):
    """
    Cryptographic erasure: overwrite LUKS header key slots and shred metadata.
    Data becomes mathematically unrecoverable even with disk recovery software.
    """
    try:
        subprocess.run(["cryptsetup", "close", volume_label], check=False)
        subprocess.run(["cryptsetup", "erase", "--batch-mode", device_node], check=True)
        subprocess.run(["shred", "-n", "3", "-z", "-s", "16M", device_node], check=False)
    except Exception as e:
        print(f"Warning during storage shredding: {e}")
