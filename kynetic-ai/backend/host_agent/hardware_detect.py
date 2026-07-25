"""
Host Agent — Hardware Detection Module.

Collects full hardware specs from the local machine using:
- psutil: CPU, RAM, disk
- pynvml (preferred) / GPUtil (fallback) / PyTorch MPS: GPU telemetry

Designed to be cross-platform: Windows, Linux, macOS.
Returns a HardwareManifest dataclass that maps directly to the backend's
HostRegistrationRequest.hardware schema.
"""

import platform
import subprocess
from dataclasses import dataclass, field

import psutil
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class GPUInfo:
    model: str
    vram_gb: float
    driver_version: str | None = None
    cuda_version: str | None = None
    temperature_c: float | None = None
    power_draw_w: float | None = None
    utilization_pct: float | None = None


@dataclass
class HardwareManifest:
    """Full hardware snapshot — matches backend HostRegistrationRequest.hardware."""
    cpu_model: str
    cpu_cores: int            # Physical cores
    cpu_threads: int          # Logical (hyperthreaded) cores
    ram_gb: float
    disk_gb: float
    disk_type: str            # 'nvme' | 'ssd' | 'hdd' | 'unknown'
    gpus: list[GPUInfo] = field(default_factory=list)
    os_type: str = "linux"    # 'windows' | 'linux' | 'macos'

    @property
    def gpu_count(self) -> int:
        return len(self.gpus)

    @property
    def primary_gpu(self) -> GPUInfo | None:
        return self.gpus[0] if self.gpus else None

    def to_api_dict(self) -> dict:
        """Convert to dict matching HostRegistrationRequest.hardware JSON shape."""
        primary = self.primary_gpu
        return {
            "cpu_model": self.cpu_model,
            "cpu_cores": self.cpu_cores,
            "cpu_threads": self.cpu_threads,
            "ram_gb": round(self.ram_gb, 2),
            "disk_type": self.disk_type,
            "disk_gb": round(self.disk_gb, 2),
            "gpu_model": primary.model if primary else None,
            "gpu_count": self.gpu_count,
            "gpu_vram_gb": round(primary.vram_gb, 2) if primary else None,
            "driver_version": primary.driver_version if primary else None,
            "cuda_version": primary.cuda_version if primary else None,
            "temperature_c": primary.temperature_c if primary else None,
            "power_draw_w": primary.power_draw_w if primary else None,
            "raw_spec": {
                "all_gpus": [
                    {
                        "model": g.model,
                        "vram_gb": g.vram_gb,
                        "driver_version": g.driver_version,
                    }
                    for g in self.gpus
                ],
                "platform": platform.platform(),
                "python_version": platform.python_version(),
            },
        }


# ---------------------------------------------------------------------------
# Disk detection helpers
# ---------------------------------------------------------------------------
def _detect_disk_type() -> tuple[float, str]:
    """Return (total_gb, disk_type) for the primary disk."""
    try:
        usage = psutil.disk_usage("/")
        total_gb = usage.total / (1024 ** 3)
    except Exception:
        total_gb = 0.0

    disk_type = "unknown"
    try:
        # On Linux: check /sys/block/sdX/queue/rotational
        import os
        for disk in psutil.disk_partitions():
            if disk.mountpoint == "/" or disk.mountpoint == "C:\\":
                dev = disk.device.split("/")[-1].rstrip("0123456789")
                rotational_path = f"/sys/block/{dev}/queue/rotational"
                if os.path.exists(rotational_path):
                    with open(rotational_path) as f:
                        rotational = f.read().strip()
                    disk_type = "hdd" if rotational == "1" else "ssd"
                    break
    except Exception:
        pass

    # Heuristic: if it's fast and the type is unknown, guess NVMe for SSDs > 500 GB
    if disk_type == "ssd" and total_gb > 200:
        try:
            result = subprocess.run(
                ["lsblk", "-d", "-o", "name,tran"],
                capture_output=True, text=True, timeout=5
            )
            if "nvme" in result.stdout.lower():
                disk_type = "nvme"
        except Exception:
            pass

    return total_gb, disk_type


# ---------------------------------------------------------------------------
# GPU detection — pynvml preferred, GPUtil fallback
# ---------------------------------------------------------------------------
def _detect_gpus_pynvml() -> list[GPUInfo]:
    """Detect NVIDIA GPUs using pynvml (most accurate)."""
    try:
        import pynvml
        pynvml.nvmlInit()
        device_count = pynvml.nvmlDeviceGetCount()
        gpus = []
        for i in range(device_count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            name = pynvml.nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode()
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            vram_gb = mem.total / (1024 ** 3)

            try:
                temp = pynvml.nvmlDeviceGetTemperature(
                    handle, pynvml.NVML_TEMPERATURE_GPU
                )
            except Exception:
                temp = None

            try:
                power = pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0  # mW → W
            except Exception:
                power = None

            try:
                util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                util_pct = util.gpu
            except Exception:
                util_pct = None

            # Driver and CUDA version (same for all GPUs on the system)
            try:
                driver = pynvml.nvmlSystemGetDriverVersion()
                if isinstance(driver, bytes):
                    driver = driver.decode()
            except Exception:
                driver = None

            gpus.append(GPUInfo(
                model=f"NVIDIA {name}",
                vram_gb=vram_gb,
                driver_version=driver,
                temperature_c=float(temp) if temp is not None else None,
                power_draw_w=power,
                utilization_pct=float(util_pct) if util_pct is not None else None,
            ))

        pynvml.nvmlShutdown()
        logger.info("gpus_detected_pynvml", count=len(gpus))
        return gpus
    except Exception as exc:
        logger.debug("pynvml_unavailable", error=str(exc))
        return []


def _detect_gpus_gputil() -> list[GPUInfo]:
    """Fallback GPU detection via GPUtil (less telemetry than pynvml)."""
    try:
        import GPUtil
        raw_gpus = GPUtil.getGPUs()
        gpus = [
            GPUInfo(
                model=g.name,
                vram_gb=g.memoryTotal / 1024.0,  # MB → GB
                temperature_c=g.temperature,
                utilization_pct=g.load * 100,
            )
            for g in raw_gpus
        ]
        logger.info("gpus_detected_gputil", count=len(gpus))
        return gpus
    except Exception as exc:
        logger.debug("gputil_unavailable", error=str(exc))
        return []


def _detect_gpus_mps() -> list[GPUInfo]:
    """Detect Apple Silicon MPS backend."""
    try:
        import torch
        if torch.backends.mps.is_available():
            chip = platform.processor() or "Apple Silicon"
            # macOS sysctl for total RAM (MPS uses unified memory)
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True, text=True, timeout=5
            )
            total_mem_gb = int(result.stdout.strip()) / (1024 ** 3) if result.returncode == 0 else 0
            return [GPUInfo(
                model=chip,
                vram_gb=round(total_mem_gb, 1),  # Unified memory
            )]
    except Exception:
        pass
    return []


def _detect_cuda_version() -> str | None:
    """Return CUDA version string if available."""
    try:
        import torch
        if torch.cuda.is_available():
            return torch.version.cuda
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Main detection function
# ---------------------------------------------------------------------------
def collect_hardware_manifest() -> HardwareManifest:
    """
    Collect a full hardware manifest from the local machine.
    Tries all GPU backends in priority order: pynvml → GPUtil → MPS.
    """
    system = platform.system().lower()
    os_type = {"windows": "windows", "linux": "linux", "darwin": "macos"}.get(system, "linux")

    # CPU
    cpu_model = platform.processor() or "Unknown CPU"
    cpu_cores = psutil.cpu_count(logical=False) or 1
    cpu_threads = psutil.cpu_count(logical=True) or cpu_cores

    # RAM
    ram = psutil.virtual_memory()
    ram_gb = ram.total / (1024 ** 3)

    # Disk
    disk_gb, disk_type = _detect_disk_type()

    # GPUs (priority: pynvml > GPUtil > MPS > none)
    gpus = _detect_gpus_pynvml()
    if not gpus:
        gpus = _detect_gpus_gputil()
    if not gpus and os_type == "macos":
        gpus = _detect_gpus_mps()

    # Inject CUDA version into GPU records if available
    cuda_version = _detect_cuda_version()
    if cuda_version:
        for g in gpus:
            g.cuda_version = cuda_version

    manifest = HardwareManifest(
        cpu_model=cpu_model,
        cpu_cores=cpu_cores,
        cpu_threads=cpu_threads,
        ram_gb=ram_gb,
        disk_gb=disk_gb,
        disk_type=disk_type,
        gpus=gpus,
        os_type=os_type,
    )

    logger.info(
        "hardware_manifest_collected",
        cpu=cpu_model,
        cpu_cores=cpu_cores,
        ram_gb=round(ram_gb, 1),
        gpu_count=len(gpus),
        gpu_models=[g.model for g in gpus],
        os=os_type,
    )
    return manifest
