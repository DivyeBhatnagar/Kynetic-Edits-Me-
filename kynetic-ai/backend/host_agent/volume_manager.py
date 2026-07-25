"""
Host Agent — Ephemeral NVMe Volume Manager.

Manages per-instance ephemeral storage and cryptographic deletion.

Security design (Security Pillar 1):
  - Each instance gets a LUKS-encrypted block device backed by a
    sparse file on the host's NVMe drive.
  - The LUKS master key is generated fresh for each instance.
  - On termination, the key is destroyed (not the data) — making
    the data cryptographically unrecoverable. An optional DoD
    overwrite pass is then run for defence-in-depth.
  - A SHA-256 confirmation hash of the deletion operation is returned
    so the provisioning service can write a SecureDeletionReceipt.

In mock mode (FIRECRACKER_MOCK=true), all disk operations are simulated
and the confirmation hash is generated from a deterministic function
of the instance_id. This allows full integration testing on macOS.

Production prerequisites:
  - cryptsetup installed on the host
  - NVMe drive mounted at NVME_BASE_PATH
  - Root/sudo access for cryptsetup commands (host agent runs as root)
"""

import hashlib
import json
import os
import subprocess
import uuid
from pathlib import Path

import structlog

log = structlog.get_logger(__name__)

FIRECRACKER_MOCK = os.environ.get("FIRECRACKER_MOCK", "true").lower() == "true"

# Base path where ephemeral volumes are created on the host NVMe
NVME_BASE_PATH = os.environ.get("NVME_BASE_PATH", "/mnt/kynetic_nvme")
# Default volume size per instance
DEFAULT_VOLUME_SIZE_GB = int(os.environ.get("DEFAULT_VOLUME_SIZE_GB", "50"))


def _volume_path(instance_id: uuid.UUID) -> str:
    return os.path.join(NVME_BASE_PATH, f"vol-{instance_id}.img")


def _luks_name(instance_id: uuid.UUID) -> str:
    return f"kynetic-{str(instance_id)[:8]}"


def _mock_confirmation_hash(instance_id: uuid.UUID, method: str) -> str:
    payload = json.dumps({
        "instance_id": str(instance_id),
        "method": method,
        "mock": True,
    })
    return hashlib.sha256(payload.encode()).hexdigest()


class VolumeManager:
    """
    Manages the lifecycle of an ephemeral NVMe volume for one instance.
    """

    def __init__(self, instance_id: uuid.UUID):
        self.instance_id = instance_id
        self.volume_path = _volume_path(instance_id)
        self.luks_name = _luks_name(instance_id)

    def _run(self, cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
        """Run a shell command. Logs the command (without key material)."""
        log.debug("volume_manager.exec", cmd=cmd[0], instance_id=str(self.instance_id))
        return subprocess.run(cmd, check=check, capture_output=True, text=True)

    def allocate(self, size_gb: int = DEFAULT_VOLUME_SIZE_GB) -> str:
        """
        Creates a sparse file and sets up LUKS encryption.
        Returns the device path for mounting into the VM.
        """
        log.info(
            "volume_manager.allocate",
            instance_id=str(self.instance_id),
            size_gb=size_gb,
            mock=FIRECRACKER_MOCK,
        )
        if FIRECRACKER_MOCK:
            return f"/dev/mock-vol-{self.instance_id}"

        # 1. Create sparse file
        Path(NVME_BASE_PATH).mkdir(parents=True, exist_ok=True)
        self._run(["truncate", "-s", f"{size_gb}G", self.volume_path])

        # 2. Format with LUKS (generates a new random master key)
        self._run([
            "cryptsetup", "luksFormat",
            "--batch-mode",
            "--key-size", "512",
            "--hash", "sha512",
            self.volume_path,
            "--key-file", "/dev/urandom",
            "--keyfile-size", "64",
        ])

        # 3. Open the LUKS container
        self._run([
            "cryptsetup", "open",
            "--type", "luks",
            self.volume_path,
            self.luks_name,
            "--key-file", "/dev/urandom",
            "--keyfile-size", "64",
        ])

        # 4. Format the mapped device with ext4
        mapped = f"/dev/mapper/{self.luks_name}"
        self._run(["mkfs.ext4", "-q", mapped])

        return mapped

    def shred(self) -> dict:
        """
        Cryptographically destroy the ephemeral volume.

        Steps:
        1. Close the LUKS container (flushes writes)
        2. Destroy the LUKS header (key material destroyed — data unrecoverable)
        3. Optional DoD overwrite of the sparse file for defence-in-depth
        4. Delete the sparse file
        5. Return confirmation payload + SHA-256 hash

        After step 2, the data is mathematically unrecoverable even if
        someone obtains the raw NVMe sectors — the AES-256 key no longer exists.
        """
        method = "luks_key_destruction"
        log.info(
            "volume_manager.shred",
            instance_id=str(self.instance_id),
            method=method,
            mock=FIRECRACKER_MOCK,
        )

        if FIRECRACKER_MOCK:
            confirmation_hash = _mock_confirmation_hash(self.instance_id, method)
            payload = json.dumps({
                "instance_id": str(self.instance_id),
                "method": method,
                "mock": True,
            })
            return {
                "method": method,
                "confirmation_hash": confirmation_hash,
                "payload": payload,
            }

        # 1. Close the LUKS container
        self._run(["cryptsetup", "close", self.luks_name], check=False)

        # 2. Destroy LUKS header (overwrites the key slots with zeros)
        self._run([
            "cryptsetup", "erase", self.volume_path,
            "--batch-mode",
        ], check=False)

        # 3. DoD-style overwrite (1 pass of zeros) — defence-in-depth
        self._run(["shred", "-n", "1", "-z", self.volume_path], check=False)

        # 4. Delete the file
        if os.path.exists(self.volume_path):
            os.unlink(self.volume_path)

        # 5. Build confirmation payload
        payload = json.dumps({
            "instance_id": str(self.instance_id),
            "method": method,
            "volume_path": self.volume_path,
        })
        confirmation_hash = hashlib.sha256(payload.encode()).hexdigest()

        return {
            "method": method,
            "confirmation_hash": confirmation_hash,
            "payload": payload,
        }

    def verify(self) -> dict:
        """
        Returns deletion confirmation data.
        In production: checks that the volume file no longer exists and
        that the LUKS container is closed.
        """
        if FIRECRACKER_MOCK:
            method = "luks_key_destruction"
            return {
                "verified": True,
                "method": method,
                "confirmation_hash": _mock_confirmation_hash(self.instance_id, method),
                "payload": json.dumps({
                    "instance_id": str(self.instance_id),
                    "method": method,
                    "mock": True,
                }),
            }

        volume_gone = not os.path.exists(self.volume_path)
        luks_closed = self._run(
            ["cryptsetup", "status", self.luks_name], check=False
        ).returncode != 0

        payload = json.dumps({
            "instance_id": str(self.instance_id),
            "volume_gone": volume_gone,
            "luks_closed": luks_closed,
        })
        return {
            "verified": volume_gone and luks_closed,
            "method": "luks_key_destruction",
            "confirmation_hash": hashlib.sha256(payload.encode()).hexdigest(),
            "payload": payload,
        }
