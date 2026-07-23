# Kynetic AI — Troubleshooting & FAQ Guide

This document provides resolutions for common issues, error codes, and operational edge cases when developing or operating Kynetic AI.

---

## 1. Docker Compose & Microservice Issues

### Issue: `database connection refused` during `docker-compose up`
- **Cause**: Microservices started before PostgreSQL initialized completely.
- **Resolution**: Microservices include automated retry loops with exponential backoff. Alternatively, restart the stack:
  ```bash
  docker-compose restart auth_service marketplace_service
  ```

### Issue: Alembic migration lock error (`Table 'alembic_version' is locked`)
- **Cause**: Previous migration process was interrupted abruptly.
- **Resolution**: Force unlock Alembic migration state:
  ```bash
  docker-compose exec auth_service python -c "from libs.db_models.database import engine; engine.execute('DELETE FROM alembic_version')"
  docker-compose exec auth_service alembic upgrade head
  ```

---

## 2. Host Agent & Hardware Probe Issues

### Issue: `pynvml.NVMLError_DriverNotLoaded` on Host Machine
- **Cause**: NVIDIA GPU drivers or CUDA toolkit are missing or incompatible.
- **Resolution**:
  1. Verify NVIDIA drivers are installed: `nvidia-smi`
  2. If running inside WSL2 or container, ensure NVIDIA Container Toolkit is enabled:
     ```bash
     distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
     curl -s -L https://nvidia.github.io/libnvidia-container/gpgkey | sudo apt-key add -
     sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
     sudo systemctl restart docker
     ```

### Issue: `eBPF XDP filter attachment failed`
- **Cause**: Linux host kernel version `< 5.4` or missing BPF kernel headers.
- **Resolution**: Upgrade kernel to `>= 5.4` (`sudo apt install linux-headers-generic`) or run host agent with `--disable-ebpf-xdp` for fallback userspace iptables filter.

---

## 3. Test Suite & Runtime Errors

### Issue: `AttributeError: module 'cryptography.hazmat...' has no attribute 'serialization'`
- **Cause**: Direct reference to `ec.serialization` instead of `from cryptography.hazmat.primitives import serialization`.
- **Resolution**: Import `serialization` directly from `cryptography.hazmat.primitives`.
