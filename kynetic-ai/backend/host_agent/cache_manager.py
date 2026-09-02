"""
Phase 4 — Kynetic LRU Cache Manager.

Enforces strict disk usage limits on the host to prevent the unbounded
disk sprawl that currently allows the ephemeral workload cache to grow
beyond 20 GB.

Design:
  - Implements an LRU (Least Recently Used) eviction policy over
    containerd image layers and ephemeral volume artefacts.
  - Configurable caps per installation profile:
      Lite:     1.0 GB ephemeral + 10 MB logs
      Standard: 5.0 GB ephemeral + 25 MB logs
      GPU:      5.0 GB ephemeral + 25 MB logs (same; model chunks are streamed)
  - Runs as a background periodic task inside the host agent daemon.
  - Integrates with ContainerdClient (container_runtime.py) to evict
    OCI image layers when the cache exceeds the configured cap.
  - Integrates with VolumeManager (volume_manager.py) to GC orphaned
    NVMe volumes from failed or abandoned instances.

Configuration (from env or /opt/kynetic/config.yaml):
  KYNETIC_CACHE_MAX_GB          default: 5.0
  KYNETIC_CACHE_MIN_FREE_GB     default: 10.0
  KYNETIC_CACHE_INTERVAL_SEC    default: 600
  KYNETIC_LOG_MAX_MB            default: 25
  KYNETIC_LOG_MAX_BACKUPS       default: 3
  KYNETIC_ORPHAN_VOLUME_DIR     default: /mnt/kynetic_nvme
"""

from __future__ import annotations

import os
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import structlog

log = structlog.get_logger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────

@dataclass
class CacheConfig:
    """
    Disk usage policy for a Kynetic host installation.

    Profiles match the tiered install profiles defined in Phase 6:
      - lite:     CPU edge nodes, constrained storage
      - standard: Standard microVM hosts
      - gpu:      Full AI/GPU rigs with bounded ephemeral cache
    """
    # Maximum size of the ephemeral workload cache (image layers + volumes)
    max_cache_size_gb: float = float(os.environ.get("KYNETIC_CACHE_MAX_GB", "5.0"))
    # Minimum free disk space to maintain at all times
    min_free_disk_gb: float = float(os.environ.get("KYNETIC_CACHE_MIN_FREE_GB", "10.0"))
    # Cache eviction check interval
    cleanup_interval_seconds: int = int(os.environ.get("KYNETIC_CACHE_INTERVAL_SEC", "600"))
    # Log rotation cap
    max_log_size_mb: int = int(os.environ.get("KYNETIC_LOG_MAX_MB", "25"))
    max_log_backup_files: int = int(os.environ.get("KYNETIC_LOG_MAX_BACKUPS", "3"))
    # Paths
    ephemeral_path: str = os.environ.get("NVME_BASE_PATH", "/mnt/kynetic_nvme")
    log_path: str = os.environ.get("KYNETIC_LOG_DIR", "/var/log/kynetic")
    # Orphan volume TTL — volumes older than this with no active instance are GC'd
    orphan_volume_ttl_hours: float = float(os.environ.get("KYNETIC_ORPHAN_TTL_HOURS", "2.0"))

    @classmethod
    def for_profile(cls, profile: str) -> "CacheConfig":
        """Return a CacheConfig tuned for the given install profile."""
        if profile == "lite":
            return cls(max_cache_size_gb=1.0, min_free_disk_gb=5.0, max_log_size_mb=10)
        elif profile == "gpu":
            return cls(max_cache_size_gb=5.0, min_free_disk_gb=15.0, max_log_size_mb=25)
        else:  # standard
            return cls(max_cache_size_gb=5.0, min_free_disk_gb=10.0, max_log_size_mb=25)


@dataclass
class CacheEntry:
    """Represents a single tracked cache artefact for LRU ordering."""
    path: str
    size_bytes: int
    last_access_time: float  # epoch seconds
    entry_type: str          # 'image_layer' | 'volume' | 'log' | 'socket'

    @property
    def size_gb(self) -> float:
        return self.size_bytes / (1024 ** 3)

    @property
    def age_hours(self) -> float:
        return (time.time() - self.last_access_time) / 3600


# ── Disk usage utilities ───────────────────────────────────────────────────────

def _dir_size_bytes(path: str) -> int:
    """Compute the total byte size of a directory tree."""
    total = 0
    try:
        for entry in Path(path).rglob("*"):
            if entry.is_file():
                try:
                    total += entry.stat().st_size
                except OSError:
                    pass
    except (PermissionError, OSError):
        pass
    return total


def _free_disk_gb(path: str) -> float:
    """Return available disk space at the given path in GB."""
    try:
        stat = shutil.disk_usage(path)
        return stat.free / (1024 ** 3)
    except OSError:
        return 0.0


def _scan_orphan_volumes(volume_dir: str, active_instance_ids: set[str]) -> list[CacheEntry]:
    """
    Scan for NVMe volume image files (vol-<uuid>.img) whose instance_id
    is no longer in the active instance set and are older than TTL.
    """
    orphans: list[CacheEntry] = []
    try:
        for p in Path(volume_dir).glob("vol-*.img"):
            try:
                stat = p.stat()
                # Extract instance_id from filename: vol-<uuid>.img
                instance_id = p.stem[4:]  # strip 'vol-' prefix
                if instance_id not in active_instance_ids:
                    orphans.append(CacheEntry(
                        path=str(p),
                        size_bytes=stat.st_size,
                        last_access_time=stat.st_atime,
                        entry_type="volume",
                    ))
            except OSError:
                pass
    except (PermissionError, OSError):
        pass
    return orphans


def _scan_stale_sockets(socket_dir: str = "/tmp") -> list[CacheEntry]:
    """Find stale Firecracker Unix domain sockets."""
    stale: list[CacheEntry] = []
    try:
        for p in Path(socket_dir).glob("firecracker-*.sock"):
            try:
                stat = p.stat()
                stale.append(CacheEntry(
                    path=str(p),
                    size_bytes=stat.st_size,
                    last_access_time=stat.st_atime,
                    entry_type="socket",
                ))
            except OSError:
                pass
    except (PermissionError, OSError):
        pass
    return stale


def _scan_log_files(log_dir: str) -> list[CacheEntry]:
    """Enumerate log files for rotation/eviction."""
    entries: list[CacheEntry] = []
    try:
        for p in Path(log_dir).rglob("*.log*"):
            try:
                stat = p.stat()
                entries.append(CacheEntry(
                    path=str(p),
                    size_bytes=stat.st_size,
                    last_access_time=stat.st_mtime,
                    entry_type="log",
                ))
            except OSError:
                pass
    except (PermissionError, OSError):
        pass
    return entries


# ── LRU Cache Manager ──────────────────────────────────────────────────────────

class CacheManager:
    """
    LRU-policy disk cache manager for the Kynetic host agent.

    Runs a periodic background task that:
      1. Measures current ephemeral cache size.
      2. Checks available free disk.
      3. If either limit is exceeded, evicts the LRU cached image layers
         (via ContainerdClient) and orphaned NVMe volumes.
      4. Rotates log files above the configured size cap.
      5. Cleans up stale Firecracker Unix domain sockets.
    """

    def __init__(
        self,
        config: CacheConfig | None = None,
        *,
        # Injectable for testing — avoids hard dep on ContainerdClient
        image_eviction_callback: Callable[[str], bool] | None = None,
        active_instance_ids_callback: Callable[[], set[str]] | None = None,
    ) -> None:
        self.config = config or CacheConfig()
        self._image_eviction_cb = image_eviction_callback
        self._active_instances_cb = active_instance_ids_callback or (lambda: set())
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._eviction_count = 0
        self._bytes_reclaimed = 0

    # ── Background loop ────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the background cache management loop."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="cache_manager",
        )
        self._thread.start()
        log.info(
            "cache_manager.started",
            max_cache_gb=self.config.max_cache_size_gb,
            min_free_gb=self.config.min_free_disk_gb,
            interval_sec=self.config.cleanup_interval_seconds,
        )

    def stop(self) -> None:
        """Stop the background loop (graceful)."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)
        log.info("cache_manager.stopped")

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.run_eviction_cycle()
            except Exception as exc:
                log.error("cache_manager.eviction_cycle_error", error=str(exc))
            self._stop_event.wait(timeout=self.config.cleanup_interval_seconds)

    # ── Eviction cycle ─────────────────────────────────────────────────────────

    def run_eviction_cycle(self) -> dict:
        """
        Run one eviction cycle. Returns a summary of actions taken.
        Can be called manually for testing or on-demand GC.
        """
        start = time.perf_counter()
        summary: dict = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "orphan_volumes_deleted": 0,
            "stale_sockets_deleted": 0,
            "log_bytes_deleted": 0,
            "images_evicted": 0,
            "bytes_reclaimed": 0,
        }

        # 1. Clean up stale Firecracker sockets
        stale_sockets = _scan_stale_sockets()
        for entry in stale_sockets:
            if entry.age_hours > 0.5:  # Sockets older than 30 minutes are stale
                try:
                    Path(entry.path).unlink(missing_ok=True)
                    summary["stale_sockets_deleted"] += 1
                    summary["bytes_reclaimed"] += entry.size_bytes
                    log.debug("cache_manager.socket_removed", path=entry.path)
                except OSError as exc:
                    log.warning("cache_manager.socket_remove_failed", path=entry.path, error=str(exc))

        # 2. Rotate oversized log files
        reclaimed_log_bytes = self._rotate_logs()
        summary["log_bytes_deleted"] = reclaimed_log_bytes
        summary["bytes_reclaimed"] += reclaimed_log_bytes

        # 3. GC orphaned NVMe volumes (instances that terminated abnormally)
        active_ids = self._active_instances_cb()
        orphan_volumes = _scan_orphan_volumes(self.config.ephemeral_path, active_ids)
        for vol in orphan_volumes:
            if vol.age_hours >= self.config.orphan_volume_ttl_hours:
                try:
                    # Issue TRIM/discard before unlinking for NVMe hygiene
                    self._trim_volume(vol.path)
                    Path(vol.path).unlink(missing_ok=True)
                    summary["orphan_volumes_deleted"] += 1
                    summary["bytes_reclaimed"] += vol.size_bytes
                    log.info(
                        "cache_manager.orphan_volume_deleted",
                        path=vol.path,
                        age_hours=round(vol.age_hours, 2),
                        size_gb=round(vol.size_gb, 3),
                    )
                except OSError as exc:
                    log.warning("cache_manager.orphan_delete_failed", path=vol.path, error=str(exc))

        # 4. Check ephemeral cache size + free disk; evict LRU images if needed
        cache_gb = _dir_size_bytes(self.config.ephemeral_path) / (1024 ** 3)
        free_gb = _free_disk_gb(self.config.ephemeral_path)

        over_size = cache_gb > self.config.max_cache_size_gb
        under_free = free_gb < self.config.min_free_disk_gb

        if (over_size or under_free) and self._image_eviction_cb:
            log.info(
                "cache_manager.lru_eviction_triggered",
                cache_gb=round(cache_gb, 2),
                free_gb=round(free_gb, 2),
                over_size=over_size,
                under_free=under_free,
            )
            evicted = self._evict_lru_images(
                target_free_gb=self.config.min_free_disk_gb + 1.0
            )
            summary["images_evicted"] = evicted

        elapsed = time.perf_counter() - start
        summary["elapsed_seconds"] = round(elapsed, 3)
        self._bytes_reclaimed += summary["bytes_reclaimed"]

        if summary["bytes_reclaimed"] > 0 or summary["images_evicted"] > 0:
            log.info("cache_manager.eviction_cycle_complete", **summary)
        else:
            log.debug("cache_manager.eviction_cycle_complete.noop", elapsed_seconds=round(elapsed, 3))

        return summary

    # ── Log rotation ───────────────────────────────────────────────────────────

    def _rotate_logs(self) -> int:
        """
        Rotate logs exceeding max_log_size_mb. Returns bytes reclaimed.
        Uses a simple rename-and-truncate strategy (no external dependency).
        """
        max_bytes = self.config.max_log_size_mb * 1024 * 1024
        reclaimed = 0
        log_entries = _scan_log_files(self.config.log_path)

        for entry in sorted(log_entries, key=lambda e: e.last_access_time):
            if entry.size_bytes > max_bytes:
                try:
                    p = Path(entry.path)
                    # Keep max_backup_files rotated copies
                    for i in range(self.config.max_log_backup_files - 1, 0, -1):
                        src = p.parent / f"{p.name}.{i}"
                        dst = p.parent / f"{p.name}.{i + 1}"
                        if src.exists():
                            src.rename(dst)
                    if p.exists():
                        p.rename(p.parent / f"{p.name}.1")
                    # Create a fresh empty log file in its place
                    p.touch()
                    reclaimed += entry.size_bytes
                    log.info(
                        "cache_manager.log_rotated",
                        path=entry.path,
                        size_mb=round(entry.size_bytes / (1024 * 1024), 2),
                    )
                except OSError as exc:
                    log.warning("cache_manager.log_rotate_failed", path=entry.path, error=str(exc))
        return reclaimed

    # ── Image LRU eviction ─────────────────────────────────────────────────────

    def _evict_lru_images(self, target_free_gb: float) -> int:
        """
        Evict images from containerd until free disk >= target_free_gb.
        Returns the number of images evicted.

        The eviction callback (image_eviction_callback) is expected to call
        ContainerdClient.remove_image(). We pass image refs to it in LRU order.
        """
        if not self._image_eviction_cb:
            return 0

        evicted = 0
        # We don't have direct access to containerd image list here without
        # importing ContainerdClient — so the callback is expected to select
        # and evict the LRU image internally and return True/False.
        # Evict up to 10 images per cycle to avoid prolonged blocking.
        for _ in range(10):
            free_gb = _free_disk_gb(self.config.ephemeral_path)
            if free_gb >= target_free_gb:
                break
            if self._image_eviction_cb("__lru__"):
                evicted += 1
            else:
                break  # No more evictable images
        return evicted

    # ── NVMe TRIM ─────────────────────────────────────────────────────────────

    def _trim_volume(self, path: str) -> None:
        """
        Issue a blkdiscard/TRIM to the volume file to free underlying NAND blocks.
        No-op if the file is not on a block device or blkdiscard is unavailable.
        """
        try:
            import subprocess
            subprocess.run(
                ["blkdiscard", path],
                capture_output=True,
                timeout=30,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    # ── Status / diagnostics ───────────────────────────────────────────────────

    def get_status(self) -> dict:
        """Return current cache status for diagnostics / heartbeat telemetry."""
        cache_bytes = _dir_size_bytes(self.config.ephemeral_path)
        free_gb = _free_disk_gb(self.config.ephemeral_path)
        log_bytes = _dir_size_bytes(self.config.log_path)

        return {
            "ephemeral_cache_gb": round(cache_bytes / (1024 ** 3), 3),
            "ephemeral_cache_max_gb": self.config.max_cache_size_gb,
            "ephemeral_cache_utilisation_pct": round(
                (cache_bytes / (1024 ** 3)) / max(self.config.max_cache_size_gb, 0.001) * 100, 1
            ),
            "free_disk_gb": round(free_gb, 2),
            "min_free_disk_gb": self.config.min_free_disk_gb,
            "log_size_mb": round(log_bytes / (1024 * 1024), 2),
            "max_log_size_mb": self.config.max_log_size_mb,
            "total_bytes_reclaimed_session": self._bytes_reclaimed,
            "background_loop_running": self._thread is not None and self._thread.is_alive(),
        }
