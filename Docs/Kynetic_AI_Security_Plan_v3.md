# Kynetic AI — Security Implementation Plan v3
## Host-Blind Confidential Compute Architecture

### Goal: A host can rent out their hardware and earn money — and never see, touch, or recover a single byte of what the developer runs on it. Not with root access. Not with physical access. Not by colluding with Kynetic itself.

---

## 0. An Honest Starting Point

Before the architecture: no legitimate security engineer will tell you a system is "unhackable" — anyone who claims that is either lying or hasn't been tested yet. What this document delivers instead is the strongest architecture that currently exists in the industry for this exact problem — the same class of technology banks, defense contractors, and confidential-computing cloud vendors (Azure Confidential Computing, AWS Nitro Enclaves, Google Confidential VMs) use to solve "I don't trust the machine my code is running on."

There is one hardware-level truth we won't hide from you or your developers: **on today's consumer GPUs (RTX 3060–4090), the GPU itself cannot cryptographically hide memory from a host with physical access** — that hardware capability only exists on NVIDIA's newest datacenter chips (H100, H200, B200 in Confidential Computing mode). So this plan builds **two honestly-labeled tiers**, not one dishonest promise:

- **Confidential Tier** — hardware-enforced, cryptographically verified, host-blind execution. True zero-trust.
- **Standard Tier** — maximum achievable isolation on consumer hardware via defense-in-depth, clearly disclosed as "strong isolation, not cryptographic host-blindness."

This honesty *is* the security feature — a platform that quietly oversells consumer-GPU isolation as "unbreakable" is a platform that gets its worst incident written up in the press. A platform that discloses tiers accurately is the one enterprises and security-conscious developers actually trust.

---

## 1. Refined Threat Model — The Adversarial Host

This plan assumes the worst-case host, not an average one:

| Adversary Capability | Assumed? |
|---|---|
| Full root/admin access to their own machine | ✅ Assumed always true |
| Modified or custom hypervisor/kernel | ✅ Assumed possible |
| Physical access to RAM, disk, PCIe bus | ✅ Assumed always true |
| Ability to attach a debugger, JTAG, or bus analyzer | ✅ Assumed possible |
| Ability to attempt cold-boot or DMA attacks | ✅ Assumed possible |
| Collusion with a Kynetic insider | ✅ Assumed possible (mitigated via Sections 6–7) |
| Nation-state-level physical hardware attacks (chip decapping) | ⚠️ Out of scope for any commercial platform — disclosed as residual risk (Section 9) |

The architecture below is built to survive everything above the line, and to transparently disclose what's below it.

---

## 2. Core Architecture — The Confidential Tier

### 2.1 Hardware Root of Trust

Every "Confidential Tier" host must pass hardware capability detection before it can ever accept a job:

- **CPU:** AMD SEV-SNP or Intel TDX — hardware-enforced memory encryption where even a compromised hypervisor cannot read guest VM memory in plaintext.
- **GPU:** NVIDIA Hopper (H100/H200) or Blackwell (B200) in **Confidential Computing mode** — encrypts GPU memory (HBM) and enforces that only an attested, authorized workload can read model weights, activations, or gradients.
- **TPM 2.0** present and enabled, used for measured boot.

```python
# host_agent/cc_capability_detector.py
"""
Runs during host onboarding (Phase 2) and on every agent restart.
Determines whether this machine is eligible for Confidential Tier.
"""
import subprocess
import pynvml

def detect_cpu_confidential_computing() -> dict:
    """Detect AMD SEV-SNP or Intel TDX support via CPUID + kernel module presence."""
    result = {"sev_snp": False, "tdx": False}
    try:
        dmesg = subprocess.run(["dmesg"], capture_output=True, text=True, timeout=5).stdout
        if "SEV-SNP" in dmesg and "enabled" in dmesg.lower():
            result["sev_snp"] = True
        if "TDX" in dmesg and "enabled" in dmesg.lower():
            result["tdx"] = True
    except Exception:
        pass
    return result

def detect_gpu_confidential_computing() -> dict:
    """Query NVML for GPU Confidential Computing capability (Hopper/Blackwell only)."""
    pynvml.nvmlInit()
    handle = pynvml.nvmlDeviceGetHandleByIndex(0)
    name = pynvml.nvmlDeviceGetName(handle)
    cc_capable = any(chip in name for chip in ["H100", "H200", "B100", "B200"])
    cc_mode_active = False
    if cc_capable:
        try:
            # NVIDIA CC mode query (via nvidia-smi conf-compute or NVML extension)
            out = subprocess.run(
                ["nvidia-smi", "conf-compute", "-f"], capture_output=True, text=True, timeout=5
            ).stdout
            cc_mode_active = "ENABLED" in out.upper()
        except Exception:
            pass
    return {"gpu_model": name, "cc_capable": cc_capable, "cc_mode_active": cc_mode_active}

def classify_host_tier() -> str:
    cpu = detect_cpu_confidential_computing()
    gpu = detect_gpu_confidential_computing()
    if (cpu["sev_snp"] or cpu["tdx"]) and gpu["cc_capable"] and gpu["cc_mode_active"]:
        return "confidential_tier"
    return "standard_tier"
```

### 2.2 Remote Attestation Gateway — No Secret Moves Until the Machine Proves Itself

This is the single most important control in the entire architecture. **Nothing sensitive — no SSH key, no dataset, no model weight, no API secret — is ever sent to a host until that specific machine has cryptographically proven, at that exact moment, that it is running genuine, unmodified, measured firmware and hypervisor code.**

```python
# services/attestation_service/attestation_gateway.py
"""
Attestation Gateway: verifies a host's hardware attestation quote (from AMD SEV-SNP,
Intel TDX, or NVIDIA GPU attestation) against the vendor's signing authority BEFORE
the Provisioning Service is permitted to release any job secrets.
"""
from cryptography.x509 import load_pem_x509_certificate
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.exceptions import InvalidSignature
import httpx

VENDOR_ROOT_CERTS = {
    "amd_sev_snp": "/etc/kynetic/certs/amd_sev_snp_root.pem",
    "intel_tdx": "/etc/kynetic/certs/intel_tdx_root.pem",
    "nvidia_gpu_cc": "/etc/kynetic/certs/nvidia_nras_root.pem",
}

class AttestationFailure(Exception):
    pass

async def verify_attestation_quote(host_id: str, quote: bytes, platform: str, expected_measurement: bytes) -> bool:
    """
    1. Verify the quote's signature chain against the hardware vendor's root of trust.
    2. Verify the reported measurement (hash of firmware/bootloader/kernel) matches
       the known-good measurement recorded when this host image was approved.
    3. Verify the quote is fresh (nonce-based, prevents replay of an old "good" quote).
    """
    root_cert_path = VENDOR_ROOT_CERTS.get(platform)
    if not root_cert_path:
        raise AttestationFailure(f"Unsupported attestation platform: {platform}")

    with open(root_cert_path, "rb") as f:
        root_cert = load_pem_x509_certificate(f.read())

    try:
        # Verify chain: quote -> platform cert -> vendor root (delegated to vendor's
        # attestation verification service where available, e.g. AMD KDS, Intel PCS,
        # NVIDIA NRAS, rather than reimplementing crypto verification locally).
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"https://vendor-attestation-verifier.internal/{platform}/verify",
                json={"quote": quote.hex(), "root_cert_fingerprint": root_cert.fingerprint},
            )
        resp.raise_for_status()
        result = resp.json()
    except (httpx.HTTPError, InvalidSignature) as e:
        raise AttestationFailure(f"Quote signature verification failed: {e}")

    if not result.get("signature_valid"):
        raise AttestationFailure("Vendor verifier rejected quote signature")

    reported_measurement = bytes.fromhex(result["measurement"])
    if reported_measurement != expected_measurement:
        raise AttestationFailure(
            "Measurement mismatch — host firmware/kernel does not match approved image. "
            "Possible tampering. Host quarantined."
        )

    return True
```

### 2.3 Sealed Secret Injection — Secrets Are Encrypted *For That Attested Environment Specifically*

Once attestation passes, secrets aren't just "sent" — they are encrypted using a key derived from the attestation quote itself, so **only that specific, verified, still-running enclave can decrypt them.** If the host tampers with the environment after attestation, the decryption key is gone.

```python
# services/attestation_service/secret_sealing.py
"""
Secrets (SSH keys, dataset decryption keys, model weight keys) are sealed
(encrypted) to the public key embedded in the hardware's attestation quote.
Only the genuine, attested enclave holds the matching private key — that
private key never leaves the CPU/GPU's protected memory.
"""
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os

def seal_secret_to_enclave(secret_bytes: bytes, enclave_public_key_der: bytes) -> bytes:
    enclave_pubkey = serialization.load_der_public_key(enclave_public_key_der)
    ephemeral_privkey = ec.generate_private_key(ec.SECP384R1())
    shared_key = ephemeral_privkey.exchange(ec.ECDH(), enclave_pubkey)

    derived_key = HKDF(
        algorithm=hashes.SHA384(), length=32, salt=None,
        info=b"kynetic-sealed-secret-v1",
    ).derive(shared_key)

    nonce = os.urandom(12)
    ciphertext = AESGCM(derived_key).encrypt(nonce, secret_bytes, associated_data=None)

    ephemeral_pubkey_bytes = ephemeral_privkey.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    # Only the attested enclave — which alone holds the matching private key
    # inside hardware-protected memory — can ever reconstruct derived_key.
    return ephemeral_pubkey_bytes + nonce + ciphertext
```

**Result:** the Kynetic control plane, the host operating system, and anyone with root on the host all see only ciphertext. There is no point in this pipeline where a plaintext SSH key, dataset key, or credential exists outside hardware-protected memory on the CPU/GPU package itself.

### 2.4 GPU Memory Encryption in Practice

On Confidential Tier hosts (H100/H200/B200 in CC mode), NVIDIA's driver stack encrypts:
- Model weights and activations in GPU HBM memory
- The PCIe link between CPU and GPU (encrypted transport, not just isolated)
- GPU-to-GPU NVLink traffic on multi-GPU jobs

Kynetic's Provisioning Service enables CC mode explicitly per job and verifies (via the GPU's own attestation report, separate from the CPU quote) that CC mode is active before releasing any model weights or datasets to the instance.

---

## 3. Standard Tier — Maximum Isolation for Consumer Hardware

For RTX 3060–4090 class hosts (the majority of the "gamer PC" supply), true hardware memory encryption isn't available — so this tier maximizes every *other* layer instead, and is explicitly labeled as such to developers.

### 3.1 Strict IOMMU / VFIO GPU Passthrough

The GPU is passed through to the guest microVM via IOMMU-isolated VFIO, not shared — this prevents the host OS from directly reading GPU memory through the driver while a job is running, and blocks DMA-based snooping from other processes on the host.

```bash
# host_agent/provisioning/vfio_passthrough.sh
# Isolates the rented GPU into its own IOMMU group before microVM start,
# unbinding it from the host's nvidia driver and binding it to vfio-pci.
GPU_PCI_ID="0000:01:00.0"
echo "$GPU_PCI_ID" > /sys/bus/pci/devices/$GPU_PCI_ID/driver/unbind
echo "vfio-pci" > /sys/bus/pci/devices/$GPU_PCI_ID/driver_override
echo "$GPU_PCI_ID" > /sys/bus/pci/drivers/vfio-pci/bind
# Result: the host kernel/OS no longer has an active driver binding to this
# GPU for the duration of the job — only the isolated microVM does.
```

### 3.2 CPU-Side Confidential Computing, Where Available Even Without GPU CC

Many consumer/workstation-class CPUs (AMD Ryzen with SEV, some Intel platforms) support *CPU* memory encryption even when the GPU doesn't support CC mode. Kynetic enables this whenever present — protecting host code, environment variables, dataset staging, and orchestration logic, even if raw GPU compute memory isn't hardware-encrypted.

### 3.3 Ephemeral, Job-Scoped Encryption Everywhere Else

```python
# services/provisioning_service/ephemeral_volume.py
"""
Every job gets a fresh LUKS-encrypted NVMe volume with a key that:
  1. Is generated fresh per job (never reused)
  2. Never touches disk in plaintext
  3. Is held only in the microVM's memory for the job's lifetime
  4. Is destroyed (not just deleted) the instant the job ends
"""
import subprocess
import secrets

def create_ephemeral_encrypted_volume(device_path: str, job_id: str) -> bytes:
    volume_key = secrets.token_bytes(64)  # 512-bit key, in-memory only
    subprocess.run(
        ["cryptsetup", "luksFormat", "--type", "luks2", "--key-file", "-", device_path],
        input=volume_key, check=True,
    )
    subprocess.run(
        ["cryptsetup", "open", "--key-file", "-", device_path, f"kynetic_{job_id}"],
        input=volume_key, check=True,
    )
    return volume_key  # passed only through sealed secret channel (Section 2.3)

def secure_destroy_volume(job_id: str, device_path: str):
    subprocess.run(["cryptsetup", "close", f"kynetic_{job_id}"], check=True)
    # Cryptographic erasure: overwrite the LUKS header (where the encrypted
    # master key lives) — this alone renders all data unrecoverable even if
    # the raw disk blocks are later recovered by the host.
    subprocess.run(["cryptsetup", "erase", "--batch-mode", device_path], check=True)
    subprocess.run(["shred", "-n", "1", "-z", device_path], check=False)
```

### 3.4 Cache & Side-Channel Isolation

To reduce cross-tenant side-channel risk (cache-timing attacks, Spectre-class leaks) even on shared consumer hardware:

- **CPU cache partitioning** (Intel CAT / AMD equivalents) allocates dedicated cache ways per job where hardware supports it.
- **Core pinning** — each job's vCPUs are pinned to dedicated physical cores, never hyperthread-shared with another tenant or the host's own processes.
- **Kernel-level Spectre/Meltdown mitigations** enforced and continuously verified as part of the Phase 3 (host verification) benchmark suite — a host reporting mitigations disabled is auto-flagged and excluded from listings until fixed.

### 3.5 Transparent Tier Labeling

```python
# libs/db_models/listing_models.py (extends Phase 3 `listings` table)
"""
security_tier column added to `listings`:
  'confidential'  -> hardware-attested, cryptographic host-blindness (Section 2)
  'standard'      -> IOMMU/VFIO isolation + ephemeral encryption, disclosed
                      as best-effort isolation, not cryptographic host-blindness
"""
```

Developers choose their tier explicitly at rental time — a fine-tuning job on public data might use Standard Tier at a lower price; a job touching proprietary model weights, health data, or customer PII is steered (with a clear UI warning, not a dark pattern) toward Confidential Tier hosts.

---

## 4. Key Management & Secrets Architecture

### 4.1 Centralized KMS/HSM

All key material that Kynetic itself ever touches — never job secrets, only the *keys that seal job secrets* — lives in a hardware security module, not application code or a database.

```python
# services/kms_service/hsm_client.py
"""
Every job gets a unique Key Encryption Key (KEK) generated inside the HSM.
The KEK never leaves the HSM in plaintext — all sealing/unsealing operations
are performed inside the HSM boundary itself.
"""
import boto3  # or hvac for HashiCorp Vault w/ HSM backend

kms = boto3.client("kms")  # backed by AWS CloudHSM or equivalent

def generate_job_kek(job_id: str) -> str:
    response = kms.create_key(
        Description=f"Kynetic job KEK - {job_id}",
        KeyUsage="ENCRYPT_DECRYPT",
        Origin="AWS_CLOUDHSM",
        Tags=[{"TagKey": "job_id", "TagValue": job_id}],
    )
    key_id = response["KeyMetadata"]["KeyId"]
    kms.put_key_policy(
        KeyId=key_id,
        PolicyName="default",
        Policy=_single_use_policy(job_id),  # key usable only by this job's
    )                                        # provisioning workflow, auto-
    return key_id                            # scheduled for deletion post-job

def schedule_kek_destruction(key_id: str):
    kms.schedule_key_deletion(KeyId=key_id, PendingWindowInDays=7)
```

### 4.2 No Standing Access, Anywhere

- No Kynetic engineer has standing production access to job secrets, developer datasets, or KEKs — access requires a logged, time-boxed, dual-approval "break-glass" procedure, itself gated behind the audit trail from Plan 2 Phase 13.
- The Host Agent binary itself never receives an unsealed secret in a form it could log, cache, or exfiltrate — sealing (Section 2.3) means the Host Agent only ever relays *ciphertext* between the control plane and the microVM's attested memory.

---

## 5. Network-Layer End-to-End Encryption

```python
# services/provisioning_service/session_tunnel.py
"""
Every developer <-> instance connection (SSH, web UI, API) tunnels through
a per-job WireGuard interface with keys generated fresh per session and
rotated on every reconnect — providing perfect forward secrecy so that even
a fully compromised key from one session cannot decrypt any other session's
traffic, past or future.
"""
import subprocess
from cryptography.hazmat.primitives.asymmetric import x25519

def generate_session_keypair():
    private_key = x25519.X25519PrivateKey.generate()
    public_key = private_key.public_key()
    return private_key, public_key

def provision_wireguard_tunnel(job_id: str, dev_pubkey: bytes, host_pubkey: bytes):
    subprocess.run([
        "wg", "set", f"kynetic-{job_id}",
        "peer", dev_pubkey.hex(),
        "allowed-ips", "10.77.0.2/32",
        "persistent-keepalive", "25",
    ], check=True)
```

- All internal service-to-service traffic (gateway → services → Host Agent) runs over mutual TLS 1.3 with certificate pinning — no plaintext internal traffic, ever, including on "trusted" internal networks.
- DNS-over-HTTPS enforced for any outbound Host Agent lookups, preventing DNS-based exfiltration or MITM redirection of a host trying to intercept control-plane traffic.

---

## 6. Continuous Re-Attestation — Trust Is Never a One-Time Check

A host proving itself genuine at job start doesn't guarantee it stays genuine for a 6-hour training run. Kynetic re-attests on an interval and kills the job the instant trust breaks.

```python
# services/attestation_service/tasks.py
"""
Celery Beat schedules this every 60 seconds for every running Confidential
Tier job, and every 5 minutes for Standard Tier jobs (checking kernel
integrity / VFIO binding state instead of a hardware quote).
"""
from celery import shared_task
from services.attestation_service.attestation_gateway import verify_attestation_quote, AttestationFailure
from services.provisioning_service.kill_switch import emergency_terminate

@shared_task
def reattest_running_job(job_id: str, host_id: str, platform: str, expected_measurement: bytes):
    quote = fetch_live_quote_from_host_agent(host_id)
    try:
        verify_attestation_quote(host_id, quote, platform, expected_measurement)
    except AttestationFailure as e:
        emergency_terminate(
            target_type="instance",
            target_id=job_id,
            reason=f"Re-attestation failed mid-job: {e}",
            triggered_by="system:attestation_monitor",
        )
        flag_host_for_security_review(host_id, reason=str(e))
```

---

## 7. Verifiable Proof for the Developer — Compute Execution Certificates

The developer shouldn't have to just take Kynetic's word for it. Every Confidential Tier job produces a cryptographically signed certificate the developer can independently verify.

```python
# services/attestation_service/execution_certificate.py
"""
Generates a signed certificate the developer can verify offline against
Kynetic's published public key — proving the job ran on genuinely attested,
CC-mode hardware for its full duration, with every re-attestation check passed.
"""
import json
import time
from cryptography.hazmat.primitives.asymmetric import ed25519

KYNETIC_SIGNING_KEY = ed25519.Ed25519PrivateKey.generate()  # HSM-backed in production

def issue_execution_certificate(job_id: str, host_id: str, measurement: bytes, attestation_log: list) -> bytes:
    payload = {
        "job_id": job_id,
        "host_id_hash": host_id,  # hashed, not raw host identity (privacy)
        "hardware_measurement": measurement.hex(),
        "security_tier": "confidential",
        "reattestation_checks_passed": len(attestation_log),
        "reattestation_checks_failed": 0,
        "issued_at": int(time.time()),
    }
    payload_bytes = json.dumps(payload, sort_keys=True).encode()
    signature = KYNETIC_SIGNING_KEY.sign(payload_bytes)
    return payload_bytes + b"." + signature
```

---

## 8. Implementation Phases (Continuing from Plan 2)

### Phase 19: Hardware Root-of-Trust Detection & Tier Classification
- **Objective**: Every host self-reports and is independently verified for Confidential vs. Standard Tier eligibility at onboarding and on every restart.
- **Key Modules**: `host_agent/cc_capability_detector.py` (Section 2.1), extended `host_service` verification flow.
- **Database Tables**: `hosts` extended with `security_tier[confidential|standard]`, `cc_hardware_report` (JSON).
- **Priority**: P0

### Phase 20: Attestation Gateway & Sealed Secret Pipeline
- **Objective**: Stand up the attestation verification service and sealed-secret delivery pipeline; no job secret leaves the control plane unsealed.
- **Key Modules**: `services/attestation_service/` (Sections 2.2, 2.3).
- **Database Tables**: `attestation_events` (`id`, `host_id`, `job_id`, `platform`, `result`, `measurement_hash`, `verified_at`).
- **Priority**: P0

### Phase 21: Confidential Tier Enablement (SEV-SNP/TDX + GPU CC Mode)
- **Objective**: Wire CPU and GPU confidential computing modes into the Provisioning Service for eligible hosts.
- **Key Modules**: Provisioning Service extensions to enable CC mode per job (Section 2.4), GPU attestation report verification.
- **Priority**: P0 for any host claiming Confidential Tier eligibility.

### Phase 22: Standard Tier Hardening (VFIO/IOMMU, Ephemeral Encryption, Cache Isolation)
- **Objective**: Implement maximum-isolation defaults for consumer hardware.
- **Key Modules**: `host_agent/provisioning/vfio_passthrough.sh`, `services/provisioning_service/ephemeral_volume.py` (Sections 3.1–3.4).
- **Priority**: P0

### Phase 23: Key Management Service (HSM-Backed)
- **Objective**: Move all key issuance off application servers and into HSM-backed KMS.
- **Key Modules**: `services/kms_service/` (Section 4).
- **Priority**: P0

### Phase 24: Continuous Re-Attestation Loop
- **Objective**: Ongoing trust verification for the full duration of every running job, not just at start.
- **Key Modules**: `services/attestation_service/tasks.py` (Section 6), Celery Beat scheduling.
- **Priority**: P0

### Phase 25: Compute Execution Certificates
- **Objective**: Give developers independently verifiable proof of the isolation their job actually ran under.
- **Key Modules**: `services/attestation_service/execution_certificate.py` (Section 7).
- **Priority**: P1

### Phase 26: Session-Layer E2E Encryption (WireGuard, mTLS 1.3, DoH)
- **Objective**: Close every remaining network-layer plaintext path.
- **Key Modules**: `services/provisioning_service/session_tunnel.py` (Section 5).
- **Priority**: P0

---

## 9. Residual Risk — What This Architecture Does *Not* Claim to Solve

Full transparency, because a security document that hides its own limits isn't a security document:

- **Standard Tier hosts remain vulnerable to a sufficiently resourced physical attacker** (cold-boot RAM extraction, hardware bus snooping) since consumer GPUs lack hardware memory encryption. Mitigation: clear tier labeling, steering sensitive workloads to Confidential Tier, and ephemeral keys that minimize the attack window.
- **Confidential Tier security depends on the vendor's (AMD/Intel/NVIDIA) implementation being sound.** Kynetic verifies attestation correctly, but a future silicon-level vulnerability in SEV-SNP/TDX/GPU-CC itself is outside Kynetic's control — mitigated by staying current on vendor security advisories and revoking trust in affected firmware measurements immediately.
- **Nation-state-level attacks (chip decapping, electron microscopy key extraction) are not defended against by any commercial platform** — this is disclosed, not hidden, and is an explicit exclusion in the Terms of Service risk disclosures (Plan 2, Phase 17).
- **Kynetic's own attestation infrastructure is itself a target.** It is protected by the same HSM/KMS discipline (Section 4), independent audit logging, and dual-approval break-glass access controls — but it remains the single most security-critical component in the whole system and warrants its own dedicated third-party penetration test before Confidential Tier is marketed publicly.

---

## 10. Verification Before This Goes Live

- [ ] Independent third-party penetration test specifically targeting the attestation gateway and secret-sealing pipeline (Sections 2.2–2.3)
- [ ] Formal/manual code review of every cryptographic function in this document by a security engineer who did not write it
- [ ] Simulated malicious-host red-team exercise: attempt DMA extraction, cold-boot attack, and VFIO escape against a live Standard Tier test instance
- [ ] Simulated attestation-bypass exercise: attempt to submit a forged or replayed quote against the Attestation Gateway
- [ ] Public bug bounty program launched before Confidential Tier is marketed as a paid, differentiated offering
- [ ] Legal/compliance review of the tier disclosure language to ensure marketing claims match actual guarantees exactly — no overstatement

---

### Closing Note

This is the architecture that gets Kynetic to "as close to unbreakable as the hardware currently allows, honestly labeled where it isn't." That honesty is not a weakness in the pitch — it's the exact quality that lets an enterprise security team say yes instead of walking away the moment they find one oversold claim.
