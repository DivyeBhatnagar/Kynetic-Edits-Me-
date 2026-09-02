"""
Phase 3 — Kynetic Container Runtime Client.

Thin Python interface to containerd via its gRPC/CRI API socket at
/run/containerd/containerd.sock. Replaces the full Docker daemon
dependency (~400 MB) with minimal containerd + runc + stargz-snapshotter
(~90 MB total).

Key capabilities:
  - Pull images via containerd's ImageService (with stargz lazy pulling)
  - Create and start containers via containerd's ContainerService
  - Attach eStargz / SOCI lazy snapshotter so images start in <2s
    without downloading their full content first
  - LRU-aware: integrates with cache_manager.py to auto-evict layers
    when disk pressure triggers

Architecture:
  Host → containerd socket → stargz-snapshotter → OCI registry (lazy)
                           ↓
                         runc (container executor)
                           ↓
                    Firecracker guest (workload)

No Docker / dockerd required. No Docker Desktop. Just:
  containerd  ~50 MB
  runc        ~15 MB
  stargz      ~25 MB
  ─────────────────
  Total:      ~90 MB  (vs ~450 MB for full Docker)

References:
  https://github.com/containerd/stargz-snapshotter
  https://github.com/containerd/containerd/tree/main/integration/client
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

CONTAINERD_SOCK = os.environ.get(
    "CONTAINERD_SOCK", "/run/containerd/containerd.sock"
)
STARGZ_SNAPSHOTTER_SOCK = os.environ.get(
    "STARGZ_SNAPSHOTTER_SOCK", "/run/containerd-stargz-grpc/containerd-stargz-grpc.sock"
)
CONTAINERD_NAMESPACE = os.environ.get("CONTAINERD_NAMESPACE", "kynetic")

# Stargz snapshotter name as registered in containerd config
STARGZ_SNAPSHOTTER_NAME = "stargz"

# Default OCI registry for workload images
DEFAULT_REGISTRY = os.environ.get("KYNETIC_REGISTRY", "registry.kynetic.ai")

# ── Runtime availability checks ───────────────────────────────────────────────


def is_containerd_available() -> bool:
    """Check if containerd socket is present and accessible."""
    sock = Path(CONTAINERD_SOCK)
    if not sock.exists():
        log.warning("containerd_sock_not_found", path=CONTAINERD_SOCK)
        return False
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(str(sock))
        s.close()
        return True
    except (OSError, ConnectionRefusedError):
        log.warning("containerd_sock_not_connectable", path=CONTAINERD_SOCK)
        return False


def is_stargz_available() -> bool:
    """Check if stargz-snapshotter socket is present."""
    return Path(STARGZ_SNAPSHOTTER_SOCK).exists()


def get_runtime_info() -> dict:
    """Return versions and availability of containerd, runc, and stargz."""
    info: dict[str, Any] = {
        "containerd_available": is_containerd_available(),
        "stargz_available": is_stargz_available(),
        "containerd_sock": CONTAINERD_SOCK,
        "stargz_sock": STARGZ_SNAPSHOTTER_SOCK,
    }
    for binary, key in [
        ("containerd", "containerd_version"),
        ("runc", "runc_version"),
        ("containerd-stargz-grpc", "stargz_version"),
    ]:
        try:
            result = subprocess.run(
                [binary, "--version"], capture_output=True, text=True, timeout=5
            )
            info[key] = result.stdout.strip() or result.stderr.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            info[key] = "not_installed"
    return info


# ── ctr CLI wrapper (thin containerd client without gRPC stub) ────────────────
# We use `ctr` (the containerd CLI) as an IPC bridge rather than importing
# the full containerd Python gRPC stubs (which would add ~20 MB to the binary).
# In production, this can be replaced with a direct gRPC call via the
# containerd API proto once grpcio is available.

class ContainerdClient:
    """
    Thin wrapper around the `ctr` CLI for containerd operations.

    Uses the stargz snapshotter by default for lazy image pulling.
    All operations run in the `kynetic` containerd namespace.
    """

    def __init__(
        self,
        namespace: str = CONTAINERD_NAMESPACE,
        snapshotter: str = STARGZ_SNAPSHOTTER_NAME,
        use_stargz: bool | None = None,
    ) -> None:
        self.namespace = namespace
        # Auto-detect stargz availability if not explicitly set
        self.snapshotter = snapshotter if (use_stargz is True or (use_stargz is None and is_stargz_available())) else "overlayfs"
        log.info(
            "containerd_client_init",
            namespace=namespace,
            snapshotter=self.snapshotter,
        )

    def _ctr(self, *args: str, input_data: str | None = None) -> subprocess.CompletedProcess:
        """Run a `ctr` CLI command in the kynetic namespace."""
        cmd = [
            "ctr",
            f"--address={CONTAINERD_SOCK}",
            f"--namespace={self.namespace}",
            *args,
        ]
        log.debug("ctr_exec", cmd=" ".join(cmd))
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            input=input_data,
            timeout=120,
        )

    # ── Image operations ───────────────────────────────────────────────────────

    def pull_image(self, image_ref: str, *, platform: str = "linux/amd64") -> dict:
        """
        Pull an OCI image via containerd with stargz lazy pulling.

        With stargz-snapshotter, the container starts in <2 seconds because
        only the image manifest and required layers are fetched on demand.
        The full image is NOT downloaded before the container starts.

        Args:
            image_ref: Full OCI image reference (e.g. 'registry.kynetic.ai/pytorch:latest')
            platform:  Target platform for multi-arch images.

        Returns:
            Dict with image digest, snapshotter used, and pull duration.
        """
        start = time.perf_counter()
        log.info("containerd.pull_image.start", image=image_ref, snapshotter=self.snapshotter)

        pull_args = [
            "images", "pull",
            f"--snapshotter={self.snapshotter}",
            f"--platform={platform}",
        ]

        # Inject registry credentials if available
        reg_user = os.environ.get("KYNETIC_REGISTRY_USER")
        reg_pass = os.environ.get("KYNETIC_REGISTRY_PASS")
        if reg_user and reg_pass:
            pull_args += [f"--user={reg_user}:{reg_pass}"]

        pull_args.append(image_ref)
        result = self._ctr(*pull_args)

        elapsed = time.perf_counter() - start

        if result.returncode != 0:
            log.error(
                "containerd.pull_image.failed",
                image=image_ref,
                stderr=result.stderr[:500],
            )
            return {
                "success": False,
                "image": image_ref,
                "error": result.stderr[:500],
                "elapsed_seconds": round(elapsed, 2),
            }

        log.info(
            "containerd.pull_image.done",
            image=image_ref,
            snapshotter=self.snapshotter,
            elapsed_seconds=round(elapsed, 2),
        )
        return {
            "success": True,
            "image": image_ref,
            "snapshotter": self.snapshotter,
            "lazy": self.snapshotter == STARGZ_SNAPSHOTTER_NAME,
            "elapsed_seconds": round(elapsed, 2),
            "stdout": result.stdout.strip(),
        }

    def list_images(self) -> list[dict]:
        """List all images in the kynetic containerd namespace."""
        result = self._ctr("images", "list", "--format=json")
        if result.returncode != 0:
            return []
        images = []
        for line in result.stdout.strip().splitlines():
            try:
                images.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        return images

    def remove_image(self, image_ref: str) -> bool:
        """Remove an image from the containerd image store (LRU eviction)."""
        result = self._ctr("images", "remove", image_ref)
        if result.returncode == 0:
            log.info("containerd.image_removed", image=image_ref)
            return True
        log.warning("containerd.image_remove_failed", image=image_ref, stderr=result.stderr[:200])
        return False

    # ── Container operations ───────────────────────────────────────────────────

    def run_container(
        self,
        image_ref: str,
        container_id: str,
        *,
        env: dict[str, str] | None = None,
        mounts: list[dict] | None = None,
        cmd: list[str] | None = None,
        cpu_quota: int | None = None,
        memory_limit_mb: int | None = None,
    ) -> dict:
        """
        Create and start a container via containerd's task API.

        Args:
            image_ref:       OCI image reference (should already be pulled/lazy)
            container_id:    Unique container identifier
            env:             Environment variables to inject
            mounts:          List of bind mounts: [{"host": "/src", "guest": "/dst", "readonly": False}]
            cmd:             Override the image entrypoint command
            cpu_quota:       CPU quota in microseconds (cgroups v2)
            memory_limit_mb: Memory limit in MB (cgroups v2)
        """
        start = time.perf_counter()
        log.info(
            "containerd.run_container",
            container_id=container_id,
            image=image_ref,
        )

        run_args = [
            "run",
            "--detach",
            f"--snapshotter={self.snapshotter}",
        ]

        # Environment variables
        for key, value in (env or {}).items():
            run_args += [f"--env={key}={value}"]

        # Bind mounts
        for mount in (mounts or []):
            ro = ":ro" if mount.get("readonly", False) else ""
            run_args += [f"--mount=type=bind,src={mount['host']},dst={mount['guest']},options=rbind{ro}"]

        # Resource limits
        if cpu_quota:
            run_args += [f"--cpu-quota={cpu_quota}"]
        if memory_limit_mb:
            run_args += [f"--memory={memory_limit_mb}m"]

        run_args += [image_ref, container_id]
        if cmd:
            run_args += cmd

        result = self._ctr(*run_args)
        elapsed = time.perf_counter() - start

        if result.returncode != 0:
            log.error(
                "containerd.run_container.failed",
                container_id=container_id,
                stderr=result.stderr[:500],
            )
            return {
                "success": False,
                "container_id": container_id,
                "error": result.stderr[:500],
                "elapsed_seconds": round(elapsed, 2),
            }

        log.info(
            "containerd.run_container.started",
            container_id=container_id,
            elapsed_seconds=round(elapsed, 2),
        )
        return {
            "success": True,
            "container_id": container_id,
            "image": image_ref,
            "snapshotter": self.snapshotter,
            "elapsed_seconds": round(elapsed, 2),
        }

    def stop_container(self, container_id: str, *, signal: str = "SIGTERM") -> bool:
        """Send a stop signal to a running container task."""
        result = self._ctr("tasks", "kill", f"--signal={signal}", container_id)
        if result.returncode == 0:
            log.info("containerd.container_stopped", container_id=container_id)
            return True
        log.warning("containerd.stop_failed", container_id=container_id, stderr=result.stderr[:200])
        return False

    def remove_container(self, container_id: str) -> bool:
        """Remove a stopped container and its task."""
        # Remove task first (no-op if already stopped)
        self._ctr("tasks", "rm", "--force", container_id)
        result = self._ctr("containers", "rm", container_id)
        if result.returncode == 0:
            log.info("containerd.container_removed", container_id=container_id)
            return True
        log.warning("containerd.remove_failed", container_id=container_id, stderr=result.stderr[:200])
        return False

    def list_containers(self) -> list[dict]:
        """List all containers in the kynetic namespace."""
        result = self._ctr("containers", "list", "--format=json")
        if result.returncode != 0:
            return []
        containers = []
        for line in result.stdout.strip().splitlines():
            try:
                containers.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        return containers

    # ── Storage diagnostics ────────────────────────────────────────────────────

    def get_snapshotter_usage(self) -> dict:
        """Return disk usage stats from the active snapshotter."""
        result = self._ctr("snapshots", "usage", "--snapshotter", self.snapshotter)
        if result.returncode != 0:
            return {"error": result.stderr[:200]}
        return {"raw": result.stdout.strip(), "snapshotter": self.snapshotter}


# ── Convenience factory ────────────────────────────────────────────────────────

def get_runtime_client() -> ContainerdClient:
    """
    Return a ContainerdClient configured for the current host environment.

    Automatically selects stargz snapshotter if available,
    falls back to overlayfs otherwise.
    """
    return ContainerdClient()
