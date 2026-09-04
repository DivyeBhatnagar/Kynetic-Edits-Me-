# Kynetic AI — Host Agent Architecture & Setup Guide

> **v7.0.0**: The Host Agent is now a native **Go** static binary (`backend/host_agent_go/`). The legacy Python `host_agent/` package is retained for reference but the Go daemon is the production runtime.

> [!IMPORTANT]
> **No Docker Desktop Required on Hosts**:
> The Host Agent operates directly at the OS level using:
> - **Firecracker microVMs** for hardware virtualization
> - **Standalone `containerd`** (~50 MB daemon) for rootfs unpacking
> - **cgo NVML (`libnvidia-ml.so`)** for direct GPU kernel communication
> Compute hosts do **NOT** need Docker Desktop or the heavy Docker daemon installed.

The **Kynetic Go Host Agent** is a single, statically-compiled binary (~14 MB) installed on hardware provider machines. It replaces the PyInstaller Python agent (~55 MB), cutting idle RAM from ~45 MB → ~10 MB and startup time from ~3s → ~50 ms.

---

## 1. Go Host Agent Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│              KYNETIC HOST AGENT DAEMON (Go static binary)              │
│                                                                        │
│  pkg/hardware/detect.go    ← /proc/cpuinfo, /sys/block, NVML cgo     │
│  pkg/benchmark/            ← NVML cgo (build tag: nvml), stub on macOS│
│  pkg/firecracker/vmm.go    ← Firecracker Go SDK, UDS socket control   │
│  pkg/volume/luks2.go       ← LUKS2 + crypto/rand key + blkdiscard    │
│  pkg/firewall/nftables.go  ← nftables via netlink (no nft subprocess) │
│  pkg/cache/lru_gc.go       ← LRU GC goroutine (replaces threading)   │
│  pkg/security/profile.go   ← Seccomp JSON + AppArmor profile writer  │
│  pkg/client/grpc_client.go ← mTLS HTTP registration + heartbeat loop │
│  cmd/agent/main.go         ← gRPC mTLS server (port 50051)           │
└────────────────────────────────────────────────────────────────────────┘
         ▲
         │  gRPC mTLS (agent_service.proto)
         │  LaunchInstance / TerminateInstance / Rebenchmark / GetStatus
         │
Python provisioning_service (gRPC client)
```

### Build Instructions

```bash
# Standard build (dev/macOS — no NVML)
cd backend/host_agent_go
go mod tidy
go build -o kynetic-agent ./cmd/agent/

# Production build (Linux + NVIDIA GPU)
CGO_ENABLED=1 go build -tags nvml \
  -ldflags="-w -s" \
  -o kynetic-agent \
  ./cmd/agent/

# Install to /usr/local/bin
sudo mv kynetic-agent /usr/local/bin/
sudo systemctl enable --now kynetic-agent
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KYNETIC_BACKEND_URL` | `https://api.kynetic.ai` | Backend API base URL |
| `KYNETIC_AGENT_DIR` | `~/.kynetic_agent` | mTLS cert directory |
| `KYNETIC_GRPC_LISTEN` | `:50051` | gRPC listen address |
| `KYNETIC_SOCK_DIR` | `/run/kynetic/vms` | Firecracker UDS socket dir |
| `KYNETIC_CACHE_DIR` | `/mnt/kynetic_cache` | NVMe image cache dir |

---

## 1b. Legacy Python Host Agent (Reference Only)

The Python `backend/host_agent/` package is retained and still functional. It is the **reference implementation** — not the production runtime after v7.0.0. Key Python files remain for:
- `hardware_detect.py` — reference for HardwareManifest schema
- `volume_manager.py` — LUKS2 reference logic
- `benchmark_runner.py` — ctypes NVML reference

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
