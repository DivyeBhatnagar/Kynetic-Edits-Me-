# Kynetic AI — Host Agent Architecture & Setup Guide

The **Kynetic Host Agent** (`backend/host_agent/`) is an ultra-lightweight daemon installed on hardware provider machines. It probes host hardware, runs native CUDA driver GEMM verification benchmarks, manages Firecracker MicroVMs with minimal Alpine rootfs assets, controls `containerd` + `stargz-snapshotter` container runtimes, handles ephemeral LUKS2 disk encryption, enforces LRU cache policies, listens on gRPC control channels, and maintains zero-trust security isolation.

With the **Phases 0–7 Host Size Optimization**, the static host disk footprint has been reduced from **~3.9 GB down to ~180 MB – 350 MB (~94% footprint reduction)**.

---

## 1. Host Agent Architecture & Core Components

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│                              KYNETIC HOST AGENT DAEMON                            │
│  - Hardware Probe (pynvml / psutil / TPM 2.0 / IOMMU)                             │
│  - Native Ctypes CUDA GEMM & NVML Benchmark Runner (Zero PyTorch Dependency)      │
│  - Containerd + Stargz Snapshotter Interface (host_agent/container_runtime.py)    │
│  - LRU Disk Cache Manager & Orphan Volume GC (host_agent/cache_manager.py)        │
│  - Firecracker MicroVM Orchestrator (rootfs-min.ext4 ~45MB, vmlinux-min ~12MB)    │
│  - gRPC / mTLS Command Channel Servicer (host_agent/command_listener.py)          │
│  - Idempotency Ring-Buffer Deduplication Store (host_agent/idempotency_store.py)  │
│  - Ephemeral LUKS2 Encryption & NVMe TRIM Sanitizer (host_agent/volume_manager.py) │
│  - eBPF XDP Network Micro-Segmentation Firewall Filter                            │
│  - Sub-Minute Continuous Re-Attestation & Auto-Kill Switch                        │
└───────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Tiered Installation Profiles & Host Onboarding

Kynetic AI provides tiered installation scripts (`infra/host_install/install_kynetic.sh`) to match different hardware tiers:

| Profile | Base Footprint | Components Included | Ideal Target |
| :--- | :---: | :--- | :--- |
| **`lite`** | **< 180 MB** | Agent binary + Firecracker + Alpine RootFS + Minimal Kernel | CPU nodes, edge devices |
| **`standard`** | **< 250 MB** | Lite + `containerd` + `runc` + `stargz-snapshotter` | Standard MicroVM hosts |
| **`gpu`** | **< 350 MB** | Standard + NVIDIA Container Toolkit hooks + 5GB LRU Cache | AI / GPU rental rigs |

### Automated Installation (Linux Ubuntu / Debian)
```bash
# Automated install script (selects profile based on GPU presence)
curl -fsSL https://install.kynetic.ai/agent | sudo bash

# Or specify profile explicitly:
sudo bash infra/host_install/install_kynetic.sh --profile standard --backend https://api.kynetic.ai
sudo bash infra/host_install/install_kynetic.sh --profile gpu
```

### Manual Installation from Source
```bash
cd backend/host_agent
pip install -r requirements.txt  # Lean requirements (psutil, httpx, structlog, pynvml, GPUtil)
python main.py --config /opt/kynetic/config.yaml
```

---

## 3. Footprint & Runtime Optimization Specification

1. **PyTorch & Redis Dependency Decoupling**: `torch` (~1.8–2.2 GB) and `redis` (~15 MB) have been removed from the host agent binary dependencies.
   - **TFLOPS Benchmarking**: Executed via direct `ctypes` bindings to host `libnvidia-ml.so` (NVML) and `libcublas.so` for raw GEMM throughput. Deep PyTorch micro-model benchmarks are run in ephemeral containers.
   - **Command Listener**: Rebenchmark RPCs route through the existing mTLS gRPC channel (`HostAgentCommandServicer`), eliminating host-side Redis pub/sub requirements.
2. **Minimal MicroVM Assets**: Replaces full 1.2 GB Ubuntu rootfs with custom Alpine 3.20 rootfs (`rootfs-min.ext4` ~45 MB, read-only shared base mount) and stripped Linux kernel (`vmlinux-min` ~12 MB).
3. **Containerd + Stargz Snapshotter**: Replaces heavy Docker Engine (~450 MB) with minimal `containerd` + `runc` + `stargz-snapshotter` (~90 MB total). Container cold starts take **< 2 seconds** via eStargz lazy image pulling.
4. **LRU Cache & Volume GC (`cache_manager.py`, `volume_manager.py`)**:
   - Caps ephemeral image cache at 1.0 GB (Lite) or 5.0 GB (Standard/GPU).
   - Automatically rotates logs at 10–25 MB caps.
   - Periodically cleans up stale Firecracker sockets in `/tmp`.
   - Scans and garbage collects orphaned NVMe volume image files (`vol-<uuid>.img`) via `blkdiscard` TRIM and `cryptsetup erase`.

---

## 4. Security & Isolation Responsibilities

1. **Hardware Root-of-Trust (`libs/security/cc_detector.py`)**: Automatically detects AMD SEV-SNP, Intel TDX, TPM 2.0, and NVIDIA Hopper/Blackwell CC mode.
2. **Ephemeral Storage (`host_agent/volume_manager.py`)**: Formats guest storage with LUKS2 512-bit master keys (held in memory only). Upon job completion, executes `cryptsetup erase` and NVMe-native `blkdiscard` TRIM sanitization.
3. **Anti-Debugging (`libs/security/anti_tamper.py`)**: Sets `prctl(PR_SET_DUMPABLE, 0)` to block host-side `ptrace` or `/proc/<pid>/mem` inspection.
4. **Network Isolation (`host_agent/network_isolation.py`)**: Configures per-instance `nftables` default-deny rulesets blocking cloud metadata endpoint `169.254.169.254` and RFC 1918 private subnets.

---

## 5. Footprint Verification & Diagnostics

### Profile Footprint Tool (`scripts/profile_footprint.py`)
```bash
python backend/host_agent/scripts/profile_footprint.py --json-out /tmp/baseline.json
```

### Post-Install Footprint Verification (`scripts/verify_footprint.py`)
```bash
python backend/host_agent/scripts/verify_footprint.py --ci
```
Checks size budgets, verifies forbidden packages (`torch`, `redis`) are not in host agent dependencies, validates service health, and asserts free disk space thresholds.
