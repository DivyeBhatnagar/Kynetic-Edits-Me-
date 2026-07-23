# Kynetic AI — Privacy Policy

**Last Updated**: July 24, 2026

Kynetic AI ("Kynetic", "we", "our") respects your privacy and is committed to protecting the personal data of Developers and Hosts using our platform.

---

## 1. Scope & Data Collected

We collect only the minimal necessary data to operate a secure compute marketplace:

### Account & Identity Data
- Email address, phone number (OTP verification), password hashes (bcrypt), and OAuth/SSO identifiers.
- GSTIN (for Indian business entities) or tax identification details for host payouts.

### Technical & Telemetry Data
- **Audit Logs (`audit_logs`)**: Timestamped security audit records of API actions, instance creation, SSH key generation, and administrative interventions.
- **Device Fingerprints (`device_fingerprints`)**: Browser hash, canvas fingerprint, user agent, and IP address collected for anti-fraud detection.
- **Host Telemetry**: Hardware benchmark metrics (GPU model, VRAM capacity, CPU core count, RAM size, NVMe benchmark speed, WireGuard NAT IP) sent by the Host Agent every 10 seconds.

---

## 2. Developer Workload & Data Privacy Guarantee

- **Zero Host File Access**: Developers' rented workloads run inside isolated Firecracker MicroVMs or rootfs-read-only Docker containers. Host machine operators have **zero access** to the developer's container filesystem, memory space, or environment variables.
- **Fernet Encrypted SSH Keys**: Ephemeral SSH key pairs generated for instance access are encrypted in transit and at rest using AES-256 Fernet keys.
- **No Workload Inspection**: Kynetic AI does not inspect, train on, or monetize developer models, code, datasets, or memory snapshots.

---

## 3. Data Retention & Deletion

- Account records are retained for the duration of the active account plus 7 years to satisfy Indian tax and financial audit requirements.
- Temporary telemetry data is purged after 30 days.
- Users may request complete account deletion by contacting `privacy@kynetic.ai`.

---

## 4. International Data Transfers & Residency

- Indian user data and tax invoices are stored strictly in AWS region `ap-south-1` (Mumbai) in compliance with the **Digital Personal Data Protection Act 2023 (DPDP Act)**.
