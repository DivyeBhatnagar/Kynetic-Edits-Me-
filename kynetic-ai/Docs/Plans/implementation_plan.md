# Kynetic AI — Host Agent Container & Runtime Size Optimization Plan

## Executive Summary & Objective

The objective is to optimize the **Kynetic AI host-side installation and container runtime footprint** from the current baseline of **~3.2 GB – 5.5 GB** down to a **permanent base installation of ~180 MB – 350 MB** (well below the <1 GB ceiling, reaching the target **250–500 MB** band), achieving an **~85% to 92% reduction in static host disk footprint**.

### Key Architectural Constraint
* **No Language Migration**: The Python-based architecture of `host_agent`, its dependencies, FastAPI/Uvicorn control planes, and Pydantic/PyInstaller pipelines are **strictly retained**.
* **Optimization Vectors**: Runtime architecture separation, lazy image pulling (`stargz-snapshotter`), minimal base rootfs/initrd, dependency decoupling (e.g. removing bundled PyTorch from the agent binary), strictly bounded LRU caching, and driver/model externalization.

---

## 1. Codebase Audit: Storage Consumers Analysis

Following an inspection of `backend/host_agent/`, `backend/services/`, `infra/`, `cli/`, and `Docs/`, the following components are responsible for host storage consumption:

```text
Component: PyTorch Bundled in Host Agent
Current size: ~1,800 MB – 2,500 MB (with CUDA/CPU wheel caches)
Why it exists: backend/host_agent/requirements.txt line 13 & benchmark_runner.py (used only for initial FP32 TFLOPS, LLM micro-model, and diffusion step benchmarks).
Whether required at runtime: NO. Only needed once during initial registration or scheduled re-benchmarks.
Whether it can be removed: YES.
Whether it can be lazy-loaded: YES (run inside an on-demand ephemeral benchmark container or replace with lightweight pure C/CUDA-driver matmul).
Whether it can be cached: N/A.
Whether it can be shared: N/A.
Recommended replacement: Pure ctypes/NVML/C-driver GEMM benchmark stub for host daemon + ephemeral containerized benchmark job.
Expected size reduction: ~1,800 MB – 2,200 MB.
```

```text
Component: Base MicroVM Root Filesystem (rootfs.ext4)
Current size: ~800 MB – 1,500 MB (Full Ubuntu/Debian server rootfs)
Why it exists: backend/host_agent/firecracker.py line 100 (/opt/kynetic/rootfs.ext4).
Whether required at runtime: YES (as base OS for Firecracker guest VMM).
Whether it can be removed: NO.
Whether it can be lazy-loaded: NO (must be locally available for instant microVM boot).
Whether it can be cached: Pre-built static read-only base image.
Whether it can be shared: Shared read-only across all microVM instances via overlay mounts.
Recommended replacement: Minimal Alpine/Busybox-based microVM rootfs with minimal init system, OpenSSH, and containerd-shim.
Expected size reduction: ~750 MB – 1,420 MB (Reduced from ~1.2 GB to ~45 MB).
```

```text
Component: MicroVM Linux Kernel (vmlinux)
Current size: ~25 MB – 45 MB (Uncompressed vmlinux with extensive hardware modules)
Why it exists: backend/host_agent/firecracker.py line 99 (/opt/kynetic/vmlinux).
Whether required at runtime: YES (Firecracker boot kernel).
Whether it can be removed: NO.
Whether it can be lazy-loaded: NO.
Whether it can be shared: Read-only shared across all microVMs.
Recommended replacement: Tailored, microVM-optimized Firecracker kernel build (virtio-net, virtio-block, virtio-vsock, no legacy drivers).
Expected size reduction: ~15 MB – 25 MB (Reduced from ~35 MB to ~12 MB).
```

```text
Component: Host Agent PyInstaller Binary & Python Libs
Current size: ~150 MB – 220 MB (Standalone kynetic-agent binary)
Why it exists: backend/host_agent/build.spec (packs Python runtime, psutil, httpx, structlog, redis, pynvml, GPUtil).
Whether required at runtime: YES (The host daemon).
Whether it can be removed: NO.
Whether it can be lazy-loaded: NO.
Whether it can be shared: N/A.
Recommended replacement: Strip unused hiddenimports, remove redis dependency (use existing mTLS gRPC/HTTP control channels in command_listener.py), compile with UPX compression.
Expected size reduction: ~100 MB – 140 MB (Reduced from ~180 MB to ~35–55 MB).
```

```text
Component: Host Docker Engine / Containerd Daemon Cache & Metadata
Current size: ~400 MB – 1,000 MB (/var/lib/docker or /var/lib/containerd base state)
Why it exists: Host container management and image layer storage.
Whether required at runtime: YES.
Whether it can be removed: Heavyweight Docker Desktop/dockerd can be replaced by standalone containerd + runc.
Whether it can be lazy-loaded: NO.
Whether it can be shared: Shared across all workloads.
Recommended replacement: Minimal containerd + runc + stargz-snapshotter daemon without full dockerd/Docker Desktop suite.
Expected size reduction: ~300 MB – 600 MB.
```

```text
Component: Workload Container Images & Cached Layers
Current size: ~5 GB – 30 GB per host (Pre-pulled PyTorch, CUDA, vLLM, Diffusers images)
Why it exists: Pre-fetching full images onto the host disk before execution.
Whether required at runtime: Required dynamically when running jobs.
Whether it can be removed: Permanent retention can be removed.
Whether it can be lazy-loaded: YES (via eStargz / Stargz Snapshotter or SOCI).
Whether it can be cached: Strictly bounded LRU cache (e.g. max 5 GB ephemeral cache).
Whether it can be shared: Shared via OCI layer content-addressable storage.
Recommended replacement: Stargz-snapshotter lazy pulling with LRU auto-pruning.
Expected size reduction: ~15 GB – 25 GB permanent disk recovery.
```

```text
Component: Unbounded Logs, Temporary Sockets & Sparse Images
Current size: ~200 MB – 2 GB (Accumulated /var/log/kynetic/, /tmp/firecracker-*.sock, failed volume artifacts)
Why it exists: Lack of strict systemd logrotate/journald limits and fallback volume deletion residue.
Whether required at runtime: NO.
Whether it can be removed: YES.
Recommended replacement: Size-capped circular log ring (50 MB cap), systemd-tmpfiles automatic socket cleanup, and deterministic orphan volume reconciliation.
Expected size reduction: ~150 MB – 1,800 MB.
```

---

## 2. Baseline & Storage Reduction Model

### Storage Footprint Baseline Comparison

| Layer / Component | Current Baseline (Estimated) | Target (Optimized Standard) | Target (Kynetic Lite) | Expected Reduction |
| :--- | :---: | :---: | :---: | :---: |
| **Host Agent Binary (`kynetic-agent`)** | 180 MB | 45 MB | 35 MB | **-75%** |
| **Agent Bundled PyTorch & Benchmarks** | 1,800 MB | 0 MB *(Externalized)* | 0 MB *(Externalized)* | **-100%** |
| **MicroVM RootFS (`rootfs.ext4`)** | 1,200 MB | 45 MB *(Alpine minimal)* | 25 MB *(Busybox initrd)* | **-96%** |
| **MicroVM Kernel (`vmlinux`)** | 35 MB | 12 MB | 12 MB | **-65%** |
| **Runtime Daemon (`containerd` + `runc` + `stargz`)** | 450 MB *(Docker)* | 90 MB *(containerd)* | 70 MB *(runc only)* | **-80%** |
| **Base Configuration, mTLS Certs, WireGuard** | 15 MB | 5 MB | 5 MB | **-66%** |
| **Default Log & Audit Ring Buffer** | 250 MB | 25 MB *(Hard capped)* | 10 MB | **-90%** |
| **Static Host Permanent Total** | **~3,930 MB (~3.9 GB)** | **~222 MB** | **~157 MB** | **~94% Reduction** |
| *Active Workload Ephemeral Cache (Configurable)* | *Unbounded (>20 GB)* | *Max 5.0 GB (LRU Cap)* | *Max 1.0 GB (LRU Cap)* | *Bounded & Evictable* |

---

## 3. Base Image & Runtime Architecture Comparison

### Base Container Image Evaluation for Host Agent & Sub-Services

| Base Image | Uncompressed Size | Compatibility with Python 3.11/3.12 & NVML | Security Posture | Build Complexity | Verdict & Rationale |
| :--- | :---: | :--- | :--- | :--- | :--- |
| **`python:3.12` (Debian Bookworm full)** | ~1,010 MB | 100% | Medium (many packages) | Low | **REJECT**: Bloated with build tools, compilers, X11, curl, git. |
| **`python:3.12-slim` (Current)** | ~130 MB | 100% | Good (glibc standard) | Low | **ACCEPTABLE (Control Plane)**: Good for central microservices, but can be improved for host agent. |
| **`python:3.12-alpine`** | ~48 MB | High (musl libc caveats with C-extensions like PyTorch) | High (minimal attack surface) | Medium | **HIGH FOR AGENT DAEMON**: Excellent for the thin host agent which only uses `pynvml`, `httpx`, `psutil`. |
| **`cgr.dev/chainguard/python:latest` (Wolfi)** | ~42 MB | 100% glibc compatible | Exceptional (Zero CVE guarantee, distroless) | Medium | **RECOMMENDED FOR HOST AGENT CONTAINER**: glibc-based, zero known CVEs, tiny footprint. |
| **Custom Minimal Rootfs (Alpine + Python 3.12)** | ~35 MB | 100% for host agent scripts | Minimal attack surface | Medium | **RECOMMENDED FOR MICROVM ROOTFS**: Base image for `/opt/kynetic/rootfs.ext4`. |

---

## 4. Architectural Transformation

```
CURRENT ARCHITECTURE (Heavyweight & Monolithic Host Install):
+-----------------------------------------------------------------------------------+
| Host Physical Machine                                                             |
|  - Full Docker Engine / Docker Desktop (~500 MB)                                  |
|  - Standalone Agent with embedded PyTorch CUDA Wheels (~2.0 GB)                   |
|  - Full Ubuntu RootFS for MicroVM (~1.2 GB)                                       |
|  - Pre-pulled Full Docker Images (~10 - 30 GB)                                    |
|  - Unbounded Ephemeral Logs & Failed Volumes                                      |
+-----------------------------------------------------------------------------------+

TARGET OPTIMIZED ARCHITECTURE:
+-----------------------------------------------------------------------------------+
| Host Physical Machine (Permanent Base Footprint: ~220 MB)                        |
|                                                                                   |
|  +-----------------------------------------------------------------------------+  |
|  | Kynetic Host Agent Daemon (Python + Ctypes NVML, ~45 MB binary)            |  |
|  |  * Registration, Health, Heartbeats, mTLS gRPC Server                       |  |
|  |  * Zero bundled PyTorch/CUDA libraries                                      |  |
|  |  * Pure NVML Driver bindings via host `libnvidia-ml.so`                     |  |
|  +-----------------------------------------------------------------------------+  |
|                                     |                                             |
|                                     v                                             |
|  +-----------------------------------------------------------------------------+  |
|  | Minimal Containerd Runtime + Stargz Snapshotter (~90 MB)                    |  |
|  |  * eStargz Lazy Image Pulling (Starts containers in <2s without full download)|  |
|  |  * Shared Content-Addressable Layer Storage (CAS) with deduplication        |  |
|  +-----------------------------------------------------------------------------+  |
|                                     |                                             |
|                                     v                                             |
|  +-----------------------------------------------------------------------------+  |
|  | Firecracker MicroVM (~12 MB vmlinux + ~45 MB Alpine rootfs)                 |  |
|  |  * In-Memory 512-bit LUKS2 Volume Mount                                     |  |
|  |  * Default-Deny nftables Isolation                                          |  |
|  +-----------------------------------------------------------------------------+  |
|                                     |                                             |
|  +----------------------------------v------------------------------------------+  |
|  | Ephemeral Storage (Bounded LRU Cache, Max 5 GB / Configurable)              |  |
|  |  - Streaming Model Chunks via FUSE (Downloaded on-demand, not permanent)    |  |
|  |  - Auto-evicted image layers & circular 25 MB log buffers                   |  |
|  +-----------------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------------+
```

---

## 5. Phased Implementation Roadmap

### Phase 0: Baseline Measurement & Profiling
* **Objective**: Measure exact byte counts of PyInstaller artifacts, rootfs image, and Docker layers.
* **Changes**:
  * Create profiling script `backend/host_agent/scripts/profile_footprint.py`.
  * Measure binary size, unpack layers, and verify runtime memory consumption.
* **Commands**:
  ```bash
  python backend/host_agent/scripts/profile_footprint.py
  ```

---

### Phase 1: Host Agent Dependency Decoupling & Binary Optimization
* **Objective**: Strip PyTorch and Redis dependencies from the permanent host agent installation; optimize PyInstaller spec.
* **Modified Files**:
  * [`backend/host_agent/requirements.txt`](file:///Users/divyebhatnagar/Desktop/KyneticSoftware/kynetic-ai/backend/host_agent/requirements.txt): Remove `torch>=2.2.0` and `redis>=5.0.4`.
  * [`backend/host_agent/benchmark_runner.py`](file:///Users/divyebhatnagar/Desktop/KyneticSoftware/kynetic-ai/backend/host_agent/benchmark_runner.py): Replace internal PyTorch calls with lightweight Ctypes CUDA GEMM invocation via `libcuda.so` / `libcublas.so` and NVML telemetry for native TFLOPS benchmarking.
  * [`backend/host_agent/agent_client.py`](file:///Users/divyebhatnagar/Desktop/KyneticSoftware/kynetic-ai/backend/host_agent/agent_client.py): Remove Redis pub/sub listener; use mTLS gRPC handler in `command_listener.py`.
  * [`backend/host_agent/build.spec`](file:///Users/divyebhatnagar/Desktop/KyneticSoftware/kynetic-ai/backend/host_agent/build.spec): Enable UPX compression (`upx=True`), exclude unused Python modules (`tkinter`, `sqlite3`, `unittest`, `email`, `html`, `pydoc`).
* **Expected Disk Reduction**: **~1.8 GB – 2.2 GB**.

---

### Phase 2: MicroVM RootFS & Kernel Optimization
* **Objective**: Replace 1.2 GB Ubuntu rootfs with custom 45 MB Alpine/musl microVM rootfs and stripped kernel.
* **New Files**:
  * `backend/host_agent/rootfs_builder/Dockerfile.rootfs`: Alpine 3.20 builder creating minimal `rootfs.ext4` containing only `/sbin/init`, `dropbear` (lightweight SSH), `runc`, and `wireguard-tools`.
  * `backend/host_agent/rootfs_builder/build_kernel.sh`: Kernel config script disabling non-virtio drivers.
* **Modified Files**:
  * [`backend/host_agent/firecracker.py`](file:///Users/divyebhatnagar/Desktop/KyneticSoftware/kynetic-ai/backend/host_agent/firecracker.py): Update default paths to `/opt/kynetic/rootfs-min.ext4` (~45 MB) and `/opt/kynetic/vmlinux-min` (~12 MB).
* **Expected Disk Reduction**: **~1.1 GB**.

---

### Phase 3: Containerd + Stargz Snapshotter (Lazy Workload Pulling)
* **Objective**: Implement eStargz / SOCI lazy image pulling so host machines never download entire multi-gigabyte container images prior to startup.
* **Modified Files**:
  * `backend/host_agent/container_runtime.py` *(New)*: Python client interfacing directly with containerd via `containerd-shim-v2` / `cri-api` Unix socket `/run/containerd/containerd.sock`.
  * `infra/host_install/install_runtime.sh` *(New)*: Standalone installation script installing minimal `containerd`, `runc`, and `stargz-snapshotter` (~90 MB total).
* **Expected Benefit**: Workload cold-start time drops from **45–120s down to 1.8–3.5s**; zero permanent image weight on host.

---

### Phase 4: Local Storage, Content-Addressable Cache & LRU Eviction
* **Objective**: Enforce strict local cache policies preventing disk sprawl from cached layers, temporary files, and dangling volumes.
* **New Files**:
  * `backend/host_agent/cache_manager.py`: Implements LRU cache manager with configurable caps (`max_size_gb`, `min_free_disk_gb`, `max_age_hours`).
* **Modified Files**:
  * [`backend/host_agent/volume_manager.py`](file:///Users/divyebhatnagar/Desktop/KyneticSoftware/kynetic-ai/backend/host_agent/volume_manager.py): Integrate periodic orphan volume scan and automated TRIM garbage collection.
* **Configuration Specification**:
  ```yaml
  kynetic_storage:
    permanent_base_path: "/opt/kynetic"
    ephemeral_workload_path: "/mnt/kynetic_nvme"
    cache:
      max_size_gb: 5.0
      min_free_disk_gb: 10.0
      eviction_policy: "LRU"
      cleanup_interval_seconds: 600
    logging:
      max_log_size_mb: 25
      max_backup_files: 3
  ```

---

### Phase 5: Dynamic AI Model Streaming (No Bundled Weights)
* **Objective**: Ensure ML weights (Safetensors / GGUF / ONNX) are never bundled into base container images or host agent packages.
* **Architecture**:
  * Workload templates mount remote model buckets via chunked FUSE streaming ([file_transfer.py](file:///Users/divyebhatnagar/Desktop/KyneticSoftware/kynetic-ai/cli/kynetic_cli/file_transfer.py) integration).
  * Layered caching stores active model chunks in the ephemeral LUKS2 volume, auto-shredded at session termination.

---

### Phase 6: Installation Profiles (Lite vs Standard vs GPU)
* **Objective**: Offer tiered host installation packages to suit edge nodes vs full GPU rental rigs.

```text
1. Kynetic Lite (<180 MB):
   - Standalone Host Agent binary (35 MB)
   - Firecracker VMM + Alpine RootFS + Minimal Kernel (70 MB)
   - Minimal WireGuard + mTLS configs (5 MB)
   - Target: CPU compute, lightweight edge tasks, low-spec hosts.

2. Kynetic Standard (<250 MB):
   - Kynetic Lite components + containerd runtime & stargz-snapshotter (90 MB)
   - Target: Standard microVM & container host nodes.

3. Kynetic AI/GPU (<350 MB permanent base + ephemeral cache):
   - Kynetic Standard + NVML driver interface + NVIDIA Container Toolkit hooks
   - Bounded 5 GB LRU ephemeral workload cache for on-demand PyTorch/CUDA images.
   - Target: Rented AI/GPU mining rigs & datacenter clusters.
```

---

### Phase 7: Production Hardening, Security & Verification
* **Security Assurances**:
  * Maintain Sigstore / Cosign image signature verification ([image_scanner.py](file:///Users/divyebhatnagar/Desktop/KyneticSoftware/kynetic-ai/backend/services/security_service/image_scanner.py)).
  * Retain `STANDARD`, `HARDENED`, and `VERIFIED` container profiles with read-only root filesystems and capability dropping ([container_profiles.py](file:///Users/divyebhatnagar/Desktop/KyneticSoftware/kynetic-ai/backend/host_agent/container_profiles.py)).
  * Retain `nftables` default-deny network isolation and cloud metadata blocking ([network_isolation.py](file:///Users/divyebhatnagar/Desktop/KyneticSoftware/kynetic-ai/backend/host_agent/network_isolation.py)).
* **Verification & Testing Plan**:
  * Benchmark script measuring exact disk consumption before and after 1st, 10th, and 50th workload execution.
  * Regression test suite: Run full pytest suite across `backend/tests/` to verify zero breaking changes in provisioning, billing, or CLI workflows.

---

## User Review Required

> [!IMPORTANT]
> **PyTorch Removal from Host Agent**: PyTorch is currently listed in `backend/host_agent/requirements.txt` exclusively for the initial onboarding benchmark run in `benchmark_runner.py`. We propose replacing this with a direct Ctypes CUDA driver benchmark stub in the host agent daemon (consuming ~0 MB) or running the PyTorch benchmark inside an ephemeral container. This is the single largest size reduction (~2 GB saved).

> [!TIP]
> **Containerd vs Full Docker**: Switching the host execution plane to use native `containerd` with `stargz-snapshotter` avoids requiring host machines to install full Docker Desktop or dockerd, saving ~400 MB of host disk space and enabling sub-3-second lazy image startups.
