# Kynetic AI — Host Agent Architecture & Setup Guide

The **Kynetic Host Agent** (`host_agent/`) is a lightweight daemon installed on hardware provider machines. It probes host hardware, runs PyTorch verification benchmarks, manages Firecracker MicroVMs, handles ephemeral LUKS2 disk encryption, and maintains zero-trust security isolation.

---

## 1. Host Agent Architecture & Core Components

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│                              KYNETIC HOST AGENT DAEMON                            │
│  - Hardware Probe (pynvml / psutil / TPM 2.0 / IOMMU)                             │
│  - Hardware Benchmark Runner (PyTorch FLOPS & VRAM Speed Test)                    │
│  - Firecracker MicroVM / gVisor Sandbox Orchestrator                              │
│  - Ephemeral LUKS2 Encryption & 3-Pass Shredder Engine                           │
│  - eBPF XDP Network Micro-Segmentation Firewall Filter                            │
│  - Sub-Minute Continuous Re-Attestation & Auto-Kill Switch                        │
└───────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Installation & Host Onboarding

### Linux Host Installation (Ubuntu / Debian / Arch)
```bash
# Download and execute the automated setup script
curl -sSL https://get.kynetic.ai/host-agent.sh | bash

# Or run manually from source:
cd host_agent
pip install -r requirements.txt
python agent.py --register --rate-usd 0.45
```

### Windows Host Installation (Windows 10 / 11 / Server)
1. Download `kynetic-host-agent.exe` signed with EV Code Signing Certificate.
2. Run installer wizard or execute via PowerShell:
   ```powershell
   .\kynetic-host-agent.exe --token <HOST_AUTH_TOKEN> --set-rate-usd 0.45
   ```

---

## 3. Security & Isolation Responsibilities

1. **Hardware Root-of-Trust (`libs/security/cc_detector.py`)**: Automatically detects AMD SEV-SNP, Intel TDX, TPM 2.0, and NVIDIA Hopper/Blackwell CC mode.
2. **Ephemeral Storage (`services/provisioning_service/ephemeral_crypto.py`)**: Formats guest storage with LUKS2 512-bit master keys. Upon job completion, executes `cryptsetup erase` and 3-pass DoD 5220.22-M shredding (`shred -n 3 -z`).
3. **Anti-Debugging (`libs/security/anti_tamper.py`)**: Sets `prctl(PR_SET_DUMPABLE, 0)` to block host-side `ptrace` or `/proc/<pid>/mem` inspection.
4. **eBPF XDP Firewall (`services/security_service/ebpf_firewall.py`)**: Hard-drops any packet targeting RFC 1918 private subnets (`192.168.0.0/16`, `10.0.0.0/8`, `172.16.0.0/12`), blocking host home Wi-Fi network scanning.
