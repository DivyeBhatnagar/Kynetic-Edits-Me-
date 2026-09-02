# Kynetic AI — Permissions & Data Protection Architecture

This document specifies the end-to-end security model, system privileges, access controls, and data protection boundaries enforced across the **User Plane** and **Host Plane** in Kynetic AI.

---

## 1. User / Developer Plane Permissions & Data Boundaries

| Control Area | Security Policy | Implementation File |
| :--- | :--- | :--- |
| **API Authentication** | • RS256/HS256 short-lived JWT Access Tokens (15-min expiry)<br>• Scoped API Key permissions (`instance:create`, `instance:terminate`, `wallet:read`, `ssh:connect`) | [`services/auth_service`](file:///Users/divyebhatnagar/Desktop/KyneticSoftware/kynetic-ai/backend/services/auth_service) |
| **SSH Key Management** | • Disposable Ed25519 SSH keypair generated in-memory<br>• Encrypted with Fernet symmetric encryption before DB persistence | [`backend/libs/common/ssh_keys.py`](file:///Users/divyebhatnagar/Desktop/KyneticSoftware/kynetic-ai/backend/libs/common/ssh_keys.py) |
| **Network Subnet Isolation** | • Dedicated WireGuard Mesh Peer IP allocation per tenant<br>• Port forwarding limited strictly to declared application ports | [`backend/libs/common/wireguard.py`](file:///Users/divyebhatnagar/Desktop/KyneticSoftware/kynetic-ai/backend/libs/common/wireguard.py) |
| **Zero Data Retention** | • All instance storage is ephemeral and encrypted<br>• Automatic non-reversible hardware TRIM wipe (`blkdiscard`) on termination | [`backend/host_agent/volume_manager.py`](file:///Users/divyebhatnagar/Desktop/KyneticSoftware/kynetic-ai/backend/host_agent/volume_manager.py) |

---

## 2. Host Node Plane Security & System Privileges

### A. Minimal System Capability Allocation
The Host Agent daemon (`kynetic-agent`) runs with bounded Linux Capabilities:
- `CAP_NET_ADMIN` — Required to configure WireGuard VPN interfaces, bridge interfaces, and `nftables` isolation rules.
- `CAP_SYS_ADMIN` — Required for LUKS2 volume formatting (`cryptsetup`) and Firecracker TAP device allocation.
- **Local Control Socket:** UNIX Domain Socket (UDS) created with file mode `0600` (accessible exclusively by root/agent user).

---

### B. LUKS2 RAM-Only Encryption & Hardware TRIM Wipe
1. **Master Key Lifecycle:**
   - Generated as a 512-bit random byte sequence directly in RAM (`os.urandom(64)`).
   - Formatted via LUKS2 (`cryptsetup luksFormat --type luks2 --cipher aes-xts-plain64 --key-size 512`).
   - Key buffer is explicit zeroized in memory upon volume mounting (`bytearray` overwrite).
2. **Deprovisioning Hardware Wipe:**
   - On instance termination, the host executes `cryptsetup erase` (destroys header and master key).
   - Issues `blkdiscard` (NVMe TRIM flash erase) to wipe physical NAND flash cells.

---

### C. Firecracker MicroVM & Container Execution Guardrails

```yaml
# Hardened Container Execution Profile (security_profile.py)
runtime: containerd + stargz-snapshotter / runc
security_options:
  - "no-new-privileges:true"                  # Prevents SUID binary privilege escalation
  - "seccomp=/etc/kynetic/kynetic-seccomp.json" # Blocks ptrace, sys_module, reboot, swap
  - "apparmor=kynetic-hardened"               # Blocks /proc, /sys, /etc/shadow access
filesystem:
  read_only_root: true                         # Read-only container root filesystem
capabilities:
  drop:
    - ALL                                      # Drops all 38 Linux capabilities by default
  add:
    - CHOWN                                    # Minimal added capabilities for app startup
    - SETUID
```

- **Firecracker KVM Boundary:**
  - Kernel: `/opt/kynetic/vmlinux-min` (read-only mount).
  - RootFS: `/opt/kynetic/rootfs-min.ext4` (Alpine minimal base, read-only mount).
- **Network Firewall (`nftables`):**
  - Default-deny policy between microVM tap devices (`vmtap0`).
  - Inter-tenant and host-loopback traffic dropped at Linux bridge level.
- **TPM 2.0 Attestation:**
  - Validates PCR 0–7 boot measurement log against signed golden hashes before node registration.

---

## 3. Host System Installation & Verification

To verify permissions and capability policies on a host node:

```bash
# Verify system capabilities assigned to host agent
getcap /usr/local/bin/kynetic-agent

# Inspect active container execution profile
ctr --namespace=kynetic container inspect <container-id> | grep -E "Capabilities|ReadonlyRootfs|NoNewPrivileges"

# List active nftables inter-VM isolation ruleset
sudo nft list ruleset
```
