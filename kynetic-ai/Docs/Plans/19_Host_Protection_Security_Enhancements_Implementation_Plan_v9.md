# Implementation Plan v9: Host Data, Hardware & Local PC Shielding Architecture

## 📌 Executive Summary
This implementation plan specifies **10 deep-tier security advancements** designed exclusively to defend the **Host's physical PC, personal filesystem, local LAN network, silicon health, and hardware telemetry** against malicious compute tenants, kernel escapes, and rogue workloads.

---

## 🏛️ 10 Security Advancements Architecture

```
                                    ┌────────────────────────────────────────────────────────┐
                                    │               Physical Host PC (Bare-Metal)            │
                                    │  - Linux IMA Kernel Integrity Validation               │
                                    │  - Disabled KSM (Anti-Spectre / Side-Channel Shield)   │
                                    │  - Dedicated Operator Emergency Hotkey (Tray Kill)     │
                                    └───────────────────────────┬────────────────────────────┘
                                                                │
                 ┌──────────────────────────────────────────────┼──────────────────────────────────────────────┐
                 ▼                                              ▼                                              ▼
┌─────────────────────────────────┐            ┌─────────────────────────────────┐            ┌─────────────────────────────────┐
│     Hardware & Silicon Guard    │            │     Network & Air-Gap Defense   │            │   Execution & Storage Sandbox   │
├─────────────────────────────────┤            ├─────────────────────────────────┤            ├─────────────────────────────────┤
│ 1. PCIe IOMMU DMA Isolation     │            │ 2. RFC1918 LAN Air-Gap Filter   │            │ 5. Rootless Mount Namespace     │
│ 4. NVML Thermal / Power Cap     │            │ 9. Host-Blind ip netns Egress   │            │ 3. eBPF LSM Syscall Enforcer    │
│ 7. Multi-Pass VRAM DMA Sanitizer│            │ 10. Memory Canary Traps         │            │ 8. Secure Boot Key Appraiser    │
└─────────────────────────────────┘            └─────────────────────────────────┘            └─────────────────────────────────┘
```

---

## 📋 Phased Implementation Breakdown

### Phase 1: PCIe IOMMU Hardware DMA Isolation (`backend/host_agent_go/pkg/hardware/iommu.go`)
* **Objective**: Hardware-level barrier preventing guest GPU firmware from executing DMA reads across host physical RAM.
* **Mechanism**:
  - Automatically inspect `/sys/kernel/iommu_groups/` during host agent startup.
  - Verify that the designated GPU and its audio controller reside in an isolated IOMMU group without sharing bridges with host NVMe or USB controllers.
  - Enforce VFIO-PCI binding with `iommu=pt` to restrict physical memory page tables strictly to guest VM RAM bounds.

### Phase 2: LAN Isolation & Local Subnet Air-Gapping (`backend/host_agent_go/pkg/firewall/lan_filter.go`)
* **Objective**: Air-gap the guest microVM from the host's private local home/office network.
* **Mechanism**:
  - Inject `nftables` bridge filter rules that explicitly drop all outbound traffic targeting RFC1918 private subnets:
    - `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`
    - Multicast/Broadcast: `224.0.0.0/4`, `255.255.255.255/32`
    - Router Admin Gateways (`192.168.1.1`, `192.168.0.1`, `10.0.0.1`)
  - All tenant network packets are constrained to the virtual tap bridge routed directly to the egress tunnel.

### Phase 3: eBPF Ring-0 System Call Threat Interceptor (`backend/host_agent_go/pkg/security/ebpf_probe.go`)
* **Objective**: In-kernel microsecond detection and prevention of container escape or privilege escalation attempts.
* **Mechanism**:
  - Load eBPF LSM programs attaching to `sys_enter_mount`, `sys_enter_ptrace`, `sys_enter_bpf`, and `security_file_open`.
  - Block attempts by the microVM worker process to access unauthorized `/dev/mem`, `/dev/kmem`, `/proc/sys`, or raw block devices.
  - Emit real-time telemetry events to `AuditLog` on anomalous syscall activity.

### Phase 4: Hardware Thermal & Silicon Burnout Governor (`backend/host_agent_go/pkg/hardware/thermal_governor.go`)
* **Objective**: Protect host GPU silicon, VRMs, and power supplies from cryptomining burnout and power virus attacks.
* **Mechanism**:
  - Continuously monitor NVML core temperature, hotspot temperature, VRAM junction temperature, fan RPM, and wattage every 2 seconds.
  - Enforce hard power caps via NVML (`nvmlDeviceSetPowerManagementLimit`).
  - Auto-Tripwire: If core temperature exceeds **83°C** or hotspot exceeds **95°C** for >15 consecutive seconds, the agent executes an emergency pause and thermal throttle before graceful workload termination.

### Phase 5: Rootless OverlayFS & Strict Storage Unsharing (`backend/host_agent_go/pkg/volume/mount_shield.go`)
* **Objective**: Guarantee zero read/write access to host `/home`, personal directories, browser caches, and SSH keys.
* **Mechanism**:
  - MicroVM daemons run in isolated user namespaces (`CLONE_NEWUSER | CLONE_NEWNS | CLONE_NEWPID`).
  - Host filesystems are completely unmounted; only an ephemeral LUKS2-encrypted ext4 image and temporary `tmpfs` mounts exist inside the mount namespace.

### Phase 6: KSM Disabling & Side-Channel Cache Shielding (`backend/host_agent_go/pkg/security/ksm_shield.go`)
* **Objective**: Prevent cross-process Spectre/Meltdown/Rowhammer cache timing side-channel leaks.
* **Mechanism**:
  - Verify `/sys/kernel/mm/ksm/run` is set to `0` (Kernel Samepage Merging disabled).
  - Pin guest microVM vCPUs to dedicated physical CPU cores (`cpuset.cpus`) separated from host personal tasks.

### Phase 7: Multi-Pass VRAM Zero-Overwriting (`backend/host_agent_go/pkg/hardware/vram_sanitizer.go`)
* **Objective**: Ensure host desktop frames, personal CAD files, or game textures in VRAM are never leaked to renters.
* **Mechanism**:
  - On instance teardown, trigger a physical PCIe bus reset (`nvidia-smi --gpu-reset`).
  - Execute a native CUDA DMA kernel filling 100% of physical VRAM with `0x00` and `0xFF` patterns.
  - Emit a signed `VRAMSanitizationReceipt` before marking the GPU available in the marketplace.

### Phase 8: Linux IMA (Integrity Measurement Architecture) Appraiser (`backend/host_agent_go/pkg/security/ima.go`)
* **Objective**: Prevent rootkits or modified binaries from executing on the host PC.
* **Mechanism**:
  - Enforce Linux kernel IMA appraisal policy (`/etc/ima/ima-policy`).
  - Verify SHA-256 binary signatures against the system's UEFI Secure Boot keys before any executable or kernel module is loaded.

### Phase 9: Host-Blind Dedicated Egress Network Namespace (`backend/host_agent_go/pkg/firewall/netns.go`)
* **Objective**: Hide the host's real residential or office IP address from the tenant and external observers.
* **Mechanism**:
  - Attach the tenant tap interface inside a dedicated Linux network namespace (`ip netns add kynetic-tenant-net`).
  - Route all tenant outbound traffic through an encrypted WireGuard proxy tunnel, masking the host's actual public IP.

### Phase 10: Physical Operator Canary Traps & Emergency Hotkey (`backend/host_agent_go/pkg/security/canary.go`)
* **Objective**: Give the host machine owner absolute veto power and immediate warning against unauthorized memory access.
* **Mechanism**:
  - Allocate protected memory canary pages at sandbox boundaries. Any write/read attempt immediately triggers a SIGSEGV and instant host quarantine.
  - Provide a lightweight system tray service / global hotkey (`Ctrl + Alt + K`) allowing the host owner to immediately terminate all active workloads and sever network interfaces with zero lag.

---

## 🧪 Verification Plan

### Automated Tests
1. **IOMMU Group Validator**: Test script checking isolation groups in `/sys/kernel/iommu_groups/`.
2. **RFC1918 LAN Packet Drop Test**: Integration test firing simulated pings to `192.168.1.1` and `10.0.0.1` and verifying 100% packet drop.
3. **Thermal Governor Unit Test**: Mock NVML temperature spikes and verify automatic throttle & tripwire event triggers.
4. **VRAM Zeroing Verification Test**: Run CUDA kernel memory read post-reset and verify 0% non-zero byte entropy.
5. **Mount Traversal Test**: Test chroot/namespace sandbox escape and verify `/home` is completely inaccessible (`ENOENT` / `EPERM`).
