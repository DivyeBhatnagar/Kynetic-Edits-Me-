# Implementation Plan v10: Host Hardware Armor, Firmware Defense & Anti-Abuse Security Architecture

## 📌 Executive Summary
This implementation plan specifies **10 deep-tier hardware, firmware, and anti-abuse security advancements** (Phases 1–10) in the native Go Host Agent (`backend/host_agent_go/`) to defend the **physical host PC, GPU firmware, DDR5/DDR4 DRAM, audio/camera peripherals, and local ISP reputation** against rogue compute tenants.

---

## 🏛️ 10 Hardware Armor Advancements

```
                                    ┌────────────────────────────────────────────────────────┐
                                    │             Physical Host Machine & Firmware           │
                                    │  - Linux Kernel Lockdown Mode (confidentiality)        │
                                    │  - Hardware Watchdog Timer (/dev/watchdog auto-reset)  │
                                    │  - TPM 2.0 PCR-Sealed Identity Vault                   │
                                    └───────────────────────────┬────────────────────────────┘
                                                                │
                 ┌──────────────────────────────────────────────┼──────────────────────────────────────────────┐
                 ▼                                              ▼                                              ▼
┌─────────────────────────────────┐            ┌─────────────────────────────────┐            ┌─────────────────────────────────┐
│     Firmware & Silicon Shield   │            │   Peripheral & Memory Security  │            │     Network & Abuse Defense     │
├─────────────────────────────────┤            ├─────────────────────────────────┤            ├─────────────────────────────────┤
│ 1. GPU VBIOS Flash Write-Lock   │            │ 2. Audio/Mic/Cam Bus Air-Gap    │            │ 4. ISP Port 25 & Anti-DDoS Guard│
│ 5. DDR5 Rowhammer / EDAC Guard  │            │ 8. cgroups v2 Fork-Bomb Sandbox │            │ 9. Telemetry Jitter Masking     │
│ 10. NVMe Controller Crypto Erase│            │                                 │            │                                 │
└─────────────────────────────────┘            └─────────────────────────────────┘            └─────────────────────────────────┘
```

---

## 📋 Phased Implementation Breakdown

### Phase 1: GPU VBIOS Flash Write-Lock (`pkg/hardware/vbios_lock.go`)
* **Objective**: Prevent rogue tenants from flashing backdoored GPU VBIOS or bricking EEPROM chips.
* **Mechanism**: Verify SPI flash write-protection status on GPU devices via NVML/sysfs, enforcing read-only firmware lock.

### Phase 2: Audio, Mic & Camera Bus Air-Gapping (`pkg/hardware/audio_airgap.go`)
* **Objective**: Eliminate acoustic side-channel snooping and camera eavesdropping.
* **Mechanism**: Explicitly unbind HD-Audio, USB audio controllers, and UVC cameras from guest PCIe/USB device trees.

### Phase 3: Linux Kernel Lockdown Mode (`pkg/security/kernel_lockdown.go`)
* **Objective**: Block unauthorized `/dev/port`, raw memory access, and unsigned module loads.
* **Mechanism**: Verify and report kernel lockdown state (`/sys/kernel/security/lockdown = [confidentiality]`).

### Phase 4: Outbound ISP Abuse & DDoS Traffic Policing (`pkg/firewall/isp_guard.go`)
* **Objective**: Protect host's residential/enterprise ISP account from blacklisting.
* **Mechanism**: Install `nftables` / `tc` filters hard-dropping outbound SMTP port 25, NetBIOS (137-139, 445), and enforcing strict PPS caps on raw sockets.

### Phase 5: DDR4/DDR5 Rowhammer & EDAC Memory Guard (`pkg/hardware/rowhammer_guard.go`)
* **Objective**: Detect DRAM bit-flip attacks and enforce Target Row Refresh (TRR) memory safety.
* **Mechanism**: Monitor `/sys/devices/system/edac/mc` memory controllers for CE/UE errors, triggering instant VM quarantine upon burst anomalies.

### Phase 6: Hardware Watchdog Timer (`pkg/security/watchdog.go`)
* **Objective**: Automatically reset or recover host from malicious kernel freeze / deadlock loops.
* **Mechanism**: Feed `/dev/watchdog` heartbeat ticker; if guest freezes system for >30s, hardware resets the sandbox.

### Phase 7: TPM 2.0 PCR-Sealed Local Vault (`pkg/security/tpm_sealed_vault.go`)
* **Objective**: Prevent theft of host mTLS certs and private keys across unauthorized boots.
* **Mechanism**: Seal and unseal host identity keys against TPM 2.0 Platform Configuration Registers (PCR 0, 2, 4, 7).

### Phase 8: cgroups v2 Fork-Bomb & Process Ceiling (`pkg/security/cgroup_limits.go`)
* **Objective**: Prevent host OS starvation from infinite process generation (`:(){ :|:& };:`).
* **Mechanism**: Configure cgroups v2 `pids.max = 1024`, `cpu.cfs_quota_us`, and `RLIMIT_NOFILE = 4096` on microVM slice.

### Phase 9: Telemetry Fan & Acoustic Side-Channel Masking (`pkg/hardware/telemetry_mask.go`)
* **Objective**: Mask host physical presence and desktop usage patterns from remote telemetry sniffers.
* **Mechanism**: Inject low-amplitude pseudo-random noise jitter into public telemetry reports.

### Phase 10: NVMe Controller-Level Cryptographic Key Erase (`pkg/volume/nvme_crypto_erase.go`)
* **Objective**: Instantly wipe physical SSD flash NAND cells in <50ms.
* **Mechanism**: Execute NVMe Format with Cryptographic Erase (`--ses=2`), generating verifiable cryptographic sanitization logs.

---

## 🧪 Verification Plan

### Automated Tests
1. **VBIOS Lock Unit Test**: Verify SPI write-protect check.
2. **Audio Air-Gap Unit Test**: Verify peripheral unbind detection.
3. **Kernel Lockdown Unit Test**: Verify `/sys/kernel/security/lockdown` reader.
4. **ISP Anti-Abuse Filter Test**: Verify port 25 and NetBIOS drop rules.
5. **Rowhammer EDAC Test**: Verify error threshold triggers and memory safety.
6. **Watchdog Heartbeat Test**: Verify watchdog ticker life-cycle.
7. **TPM Vault Test**: Verify PCR key sealing/unsealing mock logic.
8. **cgroups Ceiling Test**: Verify `pids.max` configuration generator.
9. **Telemetry Jitter Test**: Verify noise bounds on fan RPM and power draw.
10. **NVMe Crypto Erase Test**: Verify `--ses=2` format payload generation.
