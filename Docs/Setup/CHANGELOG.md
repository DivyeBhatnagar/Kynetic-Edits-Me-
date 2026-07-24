# Kynetic AI — Release Changelog

All notable changes to the **Kynetic AI** codebase across architectural phases are documented in this file.

---

## [v5.1.0] - 2026-07-24 (Control Plane Hardening & Integration Suite — Phases 27–33)
### Added
- **Business Logic Validation Layer (Phase 27)**: Atomic DB pre-flight validator gate (`validators.py`) executing 4 DB checks (requester permissions, listing availability, host status & heartbeat freshness, developer wallet balance) with exception handlers (`402`, `403`, `404`, `409`).
- **Per-Second Billing Event Bus (Phase 28)**: Internal Redis pub/sub event bus on DB 3 (`INSTANCE_RUNNING`, `INSTANCE_TERMINATED`, `INSTANCE_FAILED`), status sync publisher, `BillingMeterJob` ORM model (`0012_billing_meter_jobs.py`), 10s per-second Celery debit task, and hold refund calculation (`refund = hold - actual_billed`).
- **Host Agent Idempotent Control Channel (Phase 29)**: gRPC / mTLS control-plane contract (`proto/host_agent.proto`), `HostCommand` audit table (`0013_host_commands.py`), agent-side thread-safe idempotency ring-buffer store, and control-plane command sender (`send_launch_command`, `send_stop_command`, `send_terminate_command`).
- **Pydantic Schema Formalization (Phase 30)**: `InstanceCreateRequest` with quantization (`ROUND_HALF_UP` to `0.01`) and bounds ($0 < \text{hours} \le 720$), `InstanceActionResponse`, `InstanceConnectionResponse`.
- **Audit & Provisioning Diagnostics (Phase 31)**: `log_instance_event` and `log_validation_rejection` audit loggers writing to `audit_logs` table, and `JobDiagnostics` tracking microVM boot timing breakdown and failure stack traces.
- **Comprehensive Unit Test Suite (Phase 32)**: 82 passing unit tests covering state machine legal/illegal transitions, host agent workload engine, Fernet SSH encryption, WireGuard IP allocation, and FastAPI route handlers.
- **End-to-End Staging Integration Suite (Phase 33)**: `tests/integration/test_instance_lifecycle_e2e.py` verifying full lifecycle, validation gate rejection, host agent disconnect recovery, zero-balance auto-termination, and command channel idempotency replay protection (**88 total tests passing**).

---

## [v5.0.0] - 2026-07-24 (Security Architecture v5 — Anti-Intrusion Fortress)
### Added
- **ChaCha20 RAM Overlay (`libs/security/ram_overlay.py`)**: Cryptographic memory buffer encryption with `mlock()` and Linux `MADV_DONTDUMP` (`0x11`) to prevent Cold Boot RAM dumps and `/proc/kcore` snooping.
- **gVisor Sandbox (`libs/security/gvisor_sandbox.py`)**: Google gVisor (`runsc`) user-space Linux application kernel sandbox configuration & seccomp-BPF forbidden syscall whitelist.
- **Host Anti-Debugging (`libs/security/anti_tamper.py`)**: Host process anti-debugging policy (`prctl(PR_SET_DUMPABLE, 0)`) blocking `ptrace(PTRACE_ATTACH)` and `/proc/<pid>/mem` inspection.
- **eBPF XDP Network Firewall (`services/security_service/ebpf_firewall.py`)**: eBPF XDP kernel network micro-segmentation filter hard-dropping packets targeting RFC 1918 private subnets (`192.168.0.0/16`, `10.0.0.0/8`, `172.16.0.0/12`).
- **TPM 2.0 PCR Attestation (`libs/security/tpm_attestation.py`)**: Dynamic TPM 2.0 Platform Configuration Register quote verification with HMAC-SHA256 single-use challenge nonces.

---

## [v4.0.0] - 2026-07-23 (Security Architecture v4 — Host-Blind Zero-Trust Isolation)
### Added
- **Hardware CC Detector (`libs/security/cc_detector.py`)**: Auto-detection of AMD SEV-SNP, Intel TDX, TPM 2.0, and NVIDIA Hopper/Blackwell CC Mode to classify hardware into `confidential_tier` vs `standard_tier`.
- **Attestation Secret Sealer (`services/security_service/attestation_sealer.py`)**: ECDH (SECP384R1) + HKDF + AES-256-GCM sealed secret injection directly to enclave public keys.
- **Ephemeral Storage Shredder (`services/provisioning_service/ephemeral_crypto.py`)**: Ephemeral LUKS2 512-bit partition encryption with instant header erasure and 3-pass DoD 5220.22-M shredding (`shred -n 3 -z`).
- **Continuous Re-Attestation Loop (`services/security_service/continuous_attestation.py`)**: Sub-minute re-attestation loop triggering emergency kill-switch (<1s) on VFIO unbind or measurement drift.
- **Compute Execution Certificates (`services/security_service/execution_cert.py`)**: Ed25519 signed execution certificates issued to developers post-rental as proof of zero host intrusion.

---

## [v1.0.0 - v3.0.0] - Phases 1 – 18
### Added
- Phase 1–10: Core Platform Skeleton, Host Onboarding, Wallet Billing, Provisioning, App Templates, AI Copilot, Auto-Pricing, India Billing (UPI/GST), Observability.
- Phase 12–18: Infrastructure (Terraform/K8s/Docker Compose), Observability (Grafana/Loki/Alertmanager), QA & Chaos Validation, Next.js Admin Operations Console, Financial Double-Entry Accounting, Legal Contracts, and Next.js Frontend Portals.
