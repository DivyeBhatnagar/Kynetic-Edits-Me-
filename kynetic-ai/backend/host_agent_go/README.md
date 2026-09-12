# Kynetic Host Agent Daemon (Go Production Daemon)

[![Go Version](https://img.shields.io/badge/Go-1.22%2B-00ADD8.svg)](https://go.dev/)
[![Firecracker](https://img.shields.io/badge/Firecracker-MicroVM-orange.svg)](https://firecracker-microvm.github.io/)
[![NVIDIA NVML](https://img.shields.io/badge/NVIDIA-NVML%20cgo-76B900.svg)](https://developer.nvidia.com/management-library-nvml)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

The **Kynetic Go Host Agent** (`kynetic-host-agent`) is the production host node daemon responsible for hardware discovery, live telemetry streaming, Firecracker microVM management, zero-trust cryptographic storage shredding, and `nftables` tenant network isolation on compute provider servers.

---

## ⚡ Key Improvements: Go vs Python Host Agent

| Feature | Python Host Agent (`backend/host_agent/`) | Go Host Agent (`backend/host_agent_go/`) | Benefit |
|---|---|---|---|
| **Idle Memory Footprint** | ~45–60 MB (Python interpreter + libs) | **~10 MB** | **78% less RAM consumed** |
| **Binary Distribution** | Multi-GB venv / PyInstaller bundle | **~14 MB static binary** | Single-file zero-dependency binary |
| **Concurrency Model** | asyncio event loop + GIL bottlenecks | **Preemptive Goroutines** | Non-blocking telemetry & VMM management |
| **VMM Orchestration** | Subprocess CLI wrappers | **Native Firecracker Go SDK** | Microsecond socket control |
| **Key Zeroing** | Python garbage collection risk | **`crypto/rand` explicit zeroization** | Defense against cold-boot attacks |

---

## 🏛️ Architecture & Package Breakdown

```
backend/host_agent_go/
├── cmd/
│   └── daemon/
│       └── main.go           # Daemon lifecycle, telemetry ticker, and gRPC client loop
└── pkg/
    ├── hardware/             # NVML telemetry (temperature, clocks, VRAM, power) via cgo
    ├── benchmark/            # FP16/FP32 GEMM & VRAM memory bandwidth throughput suite
    ├── firecracker/          # MicroVM launch, tap interfaces, Alpine rootfs & containerd eStargz
    ├── volume/               # LUKS2 cryptographic volumes, key zeroing & NVMe TRIM sanitization
    ├── firewall/             # Per-tenant nftables isolation rules & cloud metadata (169.254.169.254) block
    ├── security/             # TPM 2.0 quote attestation, runtime abuse scanner & Zero Trust PDP
    ├── cache/                # Bounded LRU cache eviction (1-5 GB) & log rotation manager
    └── client/               # mTLS gRPC client connecting to Control Plane (agent_service.proto)
```

---

## 📦 Building the Host Agent

### 1. Development Build (Stubbed NVML on non-Linux)
For local development or testing without NVIDIA GPUs:

```bash
cd backend/host_agent_go
go build -o kynetic-host-agent ./cmd/daemon
```

### 2. Production Linux Build (with NVIDIA NVML)
For deploying to Ubuntu 22.04/24.04 compute nodes with CUDA and NVML:

```bash
cd backend/host_agent_go
CGO_ENABLED=1 GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -o kynetic-host-agent ./cmd/agent
```

### 3. Windows Native Build (Development / Testing)
For running natively on Windows 10/11 with simulated hardware fallbacks:

```powershell
cd backend\host_agent_go
go build -o kynetic-agent.exe ./cmd/agent
.\kynetic-agent.exe
```
*(For production compute nodes on Windows, WSL2 with NVIDIA CUDA pass-through is recommended. See [WINDOWS_SETUP_AND_RUN_GUIDE.md](../../Docs/Setup/WINDOWS_SETUP_AND_RUN_GUIDE.md))*

---

## ⚙️ Configuration & Environment Variables

| Variable | Description | Default |
|---|---|---|
| `CONTROL_PLANE_GRPC_ADDR` | Target gRPC address for the Control Plane | `localhost:50051` |
| `KYNETIC_HOST_ID` | Unique UUID / identifier for this compute host | Auto-generated |
| `KYNETIC_AUTH_TOKEN` | Host authentication secret key | (Required) |
| `FIRECRACKER_BIN_PATH` | Path to Firecracker binary | `/usr/local/bin/firecracker` |
| `FIRECRACKER_KERNEL_PATH` | Path to uncompressed guest kernel | `/var/lib/kynetic/vmlinux` |
| `FIRECRACKER_ROOTFS_PATH` | Path to base ext4 guest root filesystem | `/var/lib/kynetic/rootfs.ext4` |
| `TELEMETRY_INTERVAL_SECS` | NVML metric streaming interval | `10` |
| `STORAGE_POOL_DIR` | Directory for encrypted instance storage pools | `/var/lib/kynetic/instances` |

---

## 🛡️ Security & MicroVM Isolation Guarantees

1. **Firecracker MicroVMs**:
   - Workloads run inside dedicated KVM microVMs with sub-200ms boot times and hardware-assisted virtualization.
2. **Ephemeral LUKS2 Encryption**:
   - Instance disks are formatted with LUKS2 using 512-bit ephemeral keys generated via `crypto/rand`.
   - Keys exist solely in memory and are cryptographically scrubbed upon instance teardown.
   - Storage blocks are wiped with `blkdiscard` (NVMe TRIM) returning a signed `SecureDeletionReceipt`.
3. **nftables Network Isolation**:
   - Dedicated network namespaces and `nftables` tables per tenant.
   - Strict default-deny policy blocking access to Cloud Metadata endpoints (`169.254.169.254`) and other host services.
4. **Hardware Abuse Detection**:
   - Continuous inspection of process signatures and network traffic to block unauthorized cryptomining (`xmrig`, `ethminer`, stratum protocols).

---

## 🚀 Systemd Service Setup

Create `/etc/systemd/system/kynetic-host-agent.service`:

```ini
[Unit]
Description=Kynetic AI Host Agent Daemon
After=network.target containerd.service
Requires=containerd.service

[Service]
Type=simple
User=root
WorkingDirectory=/var/lib/kynetic
ExecStart=/usr/local/bin/kynetic-host-agent
Restart=always
RestartSec=5
Environment=CONTROL_PLANE_GRPC_ADDR=control-plane.kynetic.ai:50051
Environment=KYNETIC_AUTH_TOKEN=host_secret_key_here
LimitNOFILE=65536
LimitMEMLOCK=infinity

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now kynetic-host-agent
sudo systemctl status kynetic-host-agent
```
