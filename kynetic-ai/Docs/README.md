# Kynetic AI — Architecture & Documentation Hub

Welcome to the comprehensive documentation repository for Kynetic AI.

---

## 📚 Documentation Index

### 🏗️ Master Specifications & Architecture
- **[`Implemented_Things.md`](Implemented_Things.md)**: Exhaustive master reference covering all implemented features across Phases 1–33, Phases A–L, Phases P1–P7, v8 Features 1–7, Plan v2 Security Enhancements Parts 1–27, and the v7.0.0 Go Infrastructure Migration.
- **[`Things_Left_To_Do_Live_Production.md`](Things_Left_To_Do_Live_Production.md)**: Itemized production launch checklist, verification steps, and operational requirements.
- **[`CONTAINER_IMPLEMENTATION_AND_ARCHITECTURE.md`](CONTAINER_IMPLEMENTATION_AND_ARCHITECTURE.md)**: Deep dive into Firecracker microVMs, eStargz lazy image pulling, containerd snapshotters, and LUKS2 storage encryption.

### 🛠️ Setup & Operations (`Docs/Setup/`)
- **[`Docs/Setup/WINDOWS_SETUP_AND_RUN_GUIDE.md`](Setup/WINDOWS_SETUP_AND_RUN_GUIDE.md)**: Official Windows Operating Guide (1-Click PowerShell Setup, 100% Native No-Docker Execution, Docker Desktop, and WSL2 GPU compute nodes).
- **[`Docs/Setup/ARCHITECTURE.md`](Setup/ARCHITECTURE.md)**: Hybrid Go/Python system architecture specification, component boundaries, and communication protocols.
- **[`Docs/Setup/SETUP.md`](Setup/SETUP.md)**: Complete local development and staging deployment instructions across macOS, Linux, and Windows.
- **[`Docs/Setup/HOST_AGENT.md`](Setup/HOST_AGENT.md)**: Host node installation, Firecracker dependencies, cgo NVML configuration, and systemd daemon management.
- **[`Docs/Setup/CHANGELOG.md`](Setup/CHANGELOG.md)**: Historical release notes and version history.

### 📋 Implementation Plans (`Docs/Plans/`)
- **[`17_Kynetic_AI_Security_Enhancements_Implementation_Plan_v2.md`](Plans/17_Kynetic_AI_Security_Enhancements_Implementation_Plan_v2.md)**: Zero-Trust Security Architecture Specification (Parts 1–27).
- **[`16_Implementation_Plan_v8.md`](Plans/16_Implementation_Plan_v8.md)**: GPU Benchmarking, Rolling Health Scores, Host Reputation, Verified Hosts & Smart Search.
- **[`15_Implementation_Plan_v7.md`](Plans/15_Implementation_Plan_v7.md)**: Marketplace Payments, Double-Entry Ledger, Priority Commission & KYC Payout Engine.
- **[`14_Implementation_Plan_v6.md`](Plans/14_Implementation_Plan_v6.md)**: Core Microservices & Production Hardening Roadmap.

### 🚨 Production Runbooks (`Docs/runbooks/`)
- **[`mass-host-disconnection.md`](runbooks/mass-host-disconnection.md)**: Incident response procedures for network partitions and host disconnect floods.
- **[`high-memory-leak-in-api-gateway.md`](runbooks/high-memory-leak-in-api-gateway.md)**: Gateway diagnostics, heap profiling, and mitigation.
- **[`reputation-score-calculation-failure.md`](runbooks/reputation-score-calculation-failure.md)**: Reputation time-decay recalculation recovery.

### ⚖️ Legal & Compliance (`Docs/legal/`)
- **[`Docs/legal/`](legal/)**: Master Services Agreement, Host Provider Agreement, Privacy Policy, and Acceptable Use Policy.
