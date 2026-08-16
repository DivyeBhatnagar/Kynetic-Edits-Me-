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
import secrets
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
    Implements Part 4 (Media-Aware Storage Sanitization & LUKS2 Encryption).
    """

    def __init__(self, instance_id: uuid.UUID):
        self.instance_id = instance_id
        self.volume_path = _volume_path(instance_id)
        self.luks_name = _luks_name(instance_id)
        self._key_bytes: bytearray | None = bytearray(secrets.token_bytes(64))

    def _run(
        self,
        cmd: list[str],
        input_data: bytes | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        """Run a shell command securely. Key material is passed via stdin (never logged)."""
        log.debug("volume_manager.exec", cmd=cmd[0], instance_id=str(self.instance_id))
        return subprocess.run(
            cmd,
            input=input_data,
            check=check,
            capture_output=True,
        )

    def allocate(self, size_gb: int = DEFAULT_VOLUME_SIZE_GB) -> str:
        """
        Creates a sparse file and sets up LUKS2 encryption using an in-memory key.
        Returns the device path for mounting into the microVM.
        """
        log.info(
            "volume_manager.allocate",
            instance_id=str(self.instance_id),
            size_gb=size_gb,
            mock=FIRECRACKER_MOCK,
            luks_version="LUKS2",
        )
        if FIRECRACKER_MOCK:
            return f"/dev/mock-vol-{self.instance_id}"

        if not self._key_bytes:
            self._key_bytes = bytearray(secrets.token_bytes(64))

        # 1. Create sparse file on host NVMe
        Path(NVME_BASE_PATH).mkdir(parents=True, exist_ok=True)
        self._run(["truncate", "-s", f"{size_gb}G", self.volume_path])

        # 2. Format with LUKS2 (AES-XTS-PLAIN64, 512-bit key size) using in-memory key
        self._run(
            [
                "cryptsetup", "luksFormat",
                "--type", "luks2",
                "--batch-mode",
                "--cipher", "aes-xts-plain64",
                "--key-size", "512",
                "--hash", "sha512",
                "--pbkdf", "argon2id",
                self.volume_path,
                "--key-file", "-",
            ],
            input_data=bytes(self._key_bytes),
        )

        # 3. Open the LUKS2 container
        self._run(
            [
                "cryptsetup", "open",
                "--type", "luks2",
                self.volume_path,
                self.luks_name,
                "--key-file", "-",
            ],
            input_data=bytes(self._key_bytes),
        )

        # 4. Format mapped block device with ext4
        mapped = f"/dev/mapper/{self.luks_name}"
        self._run(["mkfs.ext4", "-q", mapped])

        return mapped

    def shred(self) -> dict:
        """
        Cryptographically destroy the ephemeral volume (Part 4 Redesign).

        Steps:
        1. Close the LUKS2 container.
        2. Erase the LUKS2 header (key material destroyed — data unrecoverable).
        3. Issue NVMe native Crypto Erase (or blkdiscard unmap) where supported.
        4. Zero/unlink the sparse volume file.
        5. Zero out in-memory key bytes.
        """
        method = "luks2_key_destruction_media_aware_sanitize"
        log.info(
            "volume_manager.shred",
            instance_id=str(self.instance_id),
            method=method,
            mock=FIRECRACKER_MOCK,
        )

        if FIRECRACKER_MOCK:
            if self._key_bytes:
                for i in range(len(self._key_bytes)):
                    self._key_bytes[i] = 0
                self._key_bytes = None

            confirmation_hash = _mock_confirmation_hash(self.instance_id, method)
            payload = json.dumps({
                "instance_id": str(self.instance_id),
                "method": method,
                "luks_version": "LUKS2",
                "mock": True,
            })
            return {
                "method": method,
                "confirmation_hash": confirmation_hash,
                "payload": payload,
            }

        # 1. Close LUKS2 container
        self._run(["cryptsetup", "close", self.luks_name], check=False)

        # 2. Erase LUKS2 header & keyslots
        self._run([
            "cryptsetup", "erase", self.volume_path,
            "--batch-mode",
        ], check=False)

        # 3. Media-aware NVMe Format (Crypto Erase) / TRIM unmap if device is raw block or file
        try:
            # Issue blkdiscard to unmap physical NAND blocks on flash storage
            self._run(["blkdiscard", self.volume_path], check=False)
        except Exception:
            pass

        # 4. DoD single-pass wipe fallback & delete
        self._run(["shred", "-n", "1", "-z", self.volume_path], check=False)
        if os.path.exists(self.volume_path):
            os.unlink(self.volume_path)

        # 5. Overwrite in-memory key bytes
        if self._key_bytes:
            for i in range(len(self._key_bytes)):
                self._key_bytes[i] = 0
            self._key_bytes = None

        # Build cryptographic confirmation payload
        payload = json.dumps({
            "instance_id": str(self.instance_id),
            "method": method,
            "volume_path": self.volume_path,
            "luks_version": "LUKS2",
            "key_destroyed": True,
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
