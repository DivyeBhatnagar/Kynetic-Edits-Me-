# Kynetic Python Host Agent (Reference & Prototyping Daemon)

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Status](https://img.shields.io/badge/Status-Reference%20%2F%20Test%20Harness-yellow.svg)]()

> [!NOTE]
> **Production Migration Notice (v7.0.0)**:
> The official production daemon for host compute nodes is the **Go Host Agent** located at [`backend/host_agent_go/`](../host_agent_go/).
> This Python implementation is retained as the architectural reference model and for executing integration test suites (`backend/tests/host_agent/`).

---

## 🏛️ Module Overview

The Python Host Agent provides a complete Python reference implementation for host node operations:

- **`daemon.py`**: Host agent lifecycle, polling, and heartbeat management.
- **`telemetry.py`**: NVML bindings via `pynvml` and `ctypes` inspecting GPU clocks, VRAM, and thermals.
- **`benchmark_suite.py`**: PyTorch-free FP16/FP32 GEMM and VRAM bandwidth benchmark suite with peer-group envelope validation.
- **`firecracker.py`**: Firecracker microVM orchestration with minimal Alpine rootfs and kernel.
- **`volume_manager.py`**: LUKS2 ephemeral disk encryption and NVMe `blkdiscard` TRIM sanitization.
- **`network_isolation.py`**: Linux `nftables` isolation rules blocking IMDS `169.254.169.254`.
- **`abuse_detector.py`**: Pre-execution OCI container scanning and cryptomining process detection.
- **`cache_manager.py`**: Bounded LRU cache eviction and log rotation.
- **`command_listener.py`**: mTLS gRPC command handler.

---

## 🧪 Running Python Host Agent Tests

```bash
DATABASE_URL="sqlite+aiosqlite:///:memory:" pytest backend/tests/test_v6_phase_d_agent_completion.py backend/tests/test_v8_feature_1_benchmark_health_score.py
```
