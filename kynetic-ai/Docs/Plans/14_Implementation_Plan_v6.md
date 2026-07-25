# Kynetic — Technical Design Document & Engineering Implementation Plan v6

### Cloud Computer Marketplace — Production Engineering Specification

> **Document type:** Technical Design Document (TDD) + Engineering Implementation Plan
> **Audience:** Senior/staff engineers implementing the platform directly
> **Style constraint:** No source code. Architecture, protocols, schemas, state machines, and sequencing only.
> **Governing principle, applied to every decision in this document:** *"Does this make the rented machine feel more like the developer's own computer?"* If a proposed feature does not pass this test, it is excluded.

---

## 1. Executive Summary

Kynetic is a **Cloud Computer Marketplace**, not an AI platform. It connects two sides of a market — people with idle GPU/CPU/RAM/storage ("Hosts") and people who need a real Linux machine right now ("Developers") — and gets a rented machine into a developer's own terminal in under a minute, with no notebooks, no web IDE, and no forced workflow.

The product surface is intentionally small:

- A **website** for authentication, browsing/renting machines, billing, and monitoring.
- A **CLI** (`kynetic`) that is the actual product: `launch`, `connect`, `stop`, `terminate`, `ls`, `status`, `logs`, `cp`, `tunnel`, `update`, `config`.
- A **Host Agent** running on every rented machine, invisible to the developer, responsible for provisioning, telemetry, PTY sessions, and lifecycle.
- A **Tunnel Gateway** that removes SSH/NAT/public-IP concerns entirely — both the CLI and the Host Agent dial *outbound* to the Gateway, which brokers the session. The developer never manages an IP address, a firewall rule, or a port-forward.

Everything downstream of `kynetic connect` is standard Linux: Docker, CUDA, `git`, `curl`, `tmux`, VS Code Remote SSH, package managers, and the public internet. Kynetic supplies compute; it never touches the developer's data, code, or models — datasets are always pulled by the developer from GitHub, Hugging Face, S3, GCS, Azure Blob, or any other origin.

This document specifies the full technical design — runtime, CLI, host agent, tunnel/connection architecture, scheduler, marketplace, billing, database, APIs, security, observability, deployment — and a phase-by-phase engineering roadmap (**Phase C onward**, continuing from prior platform-foundation phases already scoped elsewhere) that takes the platform from a working cloud-computer runtime to a production launch.

---

## 2. Product Philosophy (Engineering Interpretation)

Every subsystem below is derived from four non-negotiable product truths:

1. **The machine is the product, not a workflow.** Kynetic never renders a notebook, never wraps `python train.py` in a web form, never mediates *what* the developer runs. The Host Agent provisions a machine; it does not orchestrate a job.
2. **The terminal is the primary interface.** The CLI is engineered with the same rigor as the web control plane — not as an afterthought SDK wrapper, but as the main product surface, held to a "feels instant, feels native" bar (informed by Tailscale's and Fly.io's CLI ergonomics).
3. **Connectivity is a solved problem, invisibly.** No developer should ever type an IP address, configure a security group, or debug NAT. `kynetic connect` must work identically whether the host machine is a rack in a datacenter with a public IP or a gaming PC behind three layers of consumer NAT.
4. **Kynetic is compute, not storage.** No dataset, model weight, or checkpoint is ever uploaded to or stored by Kynetic's own infrastructure. The only persistent artifacts Kynetic's control plane stores are account, billing, marketplace, telemetry, and configuration metadata.

---

## 3. Overall Architecture

### 3.1 Component Map

```
                                   ┌────────────────────────────┐
                                   │        Website (Web)         │
                                   │  Auth · Marketplace · Billing │
                                   │  Monitoring · Launch machine  │
                                   └───────────────┬────────────┘
                                                    │ REST (JSON) + WebSocket
                                                    ▼
                          ┌───────────────────────────────────────────┐
                          │              Control Plane (API)             │
                          │  Auth · Marketplace · Scheduler · Billing    │
                          │  Instance Registry · Reputation · Telemetry  │
                          │  Store (gRPC internal, REST external)         │
                          └───────┬───────────────────┬─────────────────┘
                                  │                     │
                     mTLS/gRPC    │                     │  mTLS/gRPC (reverse-dial)
                                  ▼                     ▼
                     ┌────────────────────┐   ┌─────────────────────────┐
                     │   Tunnel Gateway     │   │       Host Agent          │
                     │  (session broker,    │◄──┤   (runs on every rented   │
                     │  relay, NAT traversal)│   │   machine, outbound-only) │
                     └─────────┬────────────┘   └─────────────┬─────────────┘
                                │                               │
                                │ mTLS/QUIC (reverse-dial)       │ local
                                ▼                               ▼
                     ┌────────────────────┐         ┌─────────────────────┐
                     │     kynetic CLI      │         │  Rented Linux Machine │
                     │ (developer's own PC)  │         │ Docker · CUDA · SSHD  │
                     └────────────────────┘         │  Workspace · GPU/CPU  │
                                                       └─────────────────────┘
```

### 3.2 Core Design Choice: Reverse-Dial Everywhere

Both the **CLI** and the **Host Agent** are pure outbound TCP/QUIC clients. Neither ever accepts an inbound connection from the internet. This single decision eliminates SSH key distribution to strangers' routers, public IP requirements for hosts, firewall configuration for developers, and an entire category of attack surface — it is the same trust model used by Tailscale's coordination server and Cloudflare Tunnel's `cloudflared` daemon, applied to compute rental instead of private networking.

- The **Host Agent**, on boot, opens a persistent authenticated stream to the **Tunnel Gateway** and holds it open (with keepalives) for the life of the instance.
- The **CLI**, on `kynetic connect`, opens its own authenticated stream to the **Tunnel Gateway**, presents an instance ID, and the Gateway **splices** the two streams into one full-duplex, multiplexed session.
- No WireGuard mesh, no STUN/TURN complexity, and no P2P NAT traversal is required for the MVP — the Gateway relay path is the only path, which is the simplest architecture that satisfies "never think about SSH, public IPs, or NAT." A direct peer-to-peer upgrade path (WireGuard-based, opportunistic) is documented as a post-MVP extension point in §20, not built at launch.

### 3.3 Primary Technology Choices

| Layer | Technology | Rationale |
|---|---|---|
| CLI | Python, packaged as a single-file executable per OS/arch via PyInstaller | Fast to develop and extend; PyInstaller freezes the interpreter + dependencies into one self-contained binary so the developer never needs a local Python install — matches the "just run one binary" ergonomics of Tailscale/Fly CLIs while keeping the whole codebase in one language |
| Host Agent | Python, packaged as a single-file executable via PyInstaller; `asyncio` for concurrent I/O | Same packaging rationale; must run unmodified across arbitrary host machines with minimal footprint and no assumed system Python |
| Tunnel Gateway | Python, `grpc.aio` (asyncio-based gRPC) bidirectional streaming over mTLS (QUIC transport via `aioquic`) | High-concurrency multiplexed stream brokering built on `asyncio`'s event loop; QUIC tolerates flaky consumer networks (gaming PCs, home ISPs) better than raw TCP |
| Control Plane (API) | Python (FastAPI) services, `grpc.aio` internally, REST/JSON externally via FastAPI | Consistent language across the whole backend simplifies operations, shared libraries, and on-call; FastAPI's async support keeps I/O-bound request handling performant |
| CLI framework | Typer (built on Click) | Ergonomic command/subcommand definitions with type-hint-driven argument parsing, matching the `kynetic <verb>` command style |
| Primary database | PostgreSQL, accessed via SQLAlchemy 2.0 (async) + Alembic migrations | Strong relational guarantees for billing ledger, instance registry, marketplace state |
| Cache / pub-sub / queue | Redis | Session cache, scheduler working set, pub-sub for real-time status fan-out, backing store for Celery |
| Background task queue | Celery (Redis broker) | Scheduled jobs — heartbeat processing, reputation recomputation, benchmark re-runs, payout batching, ledger reconciliation |
| Container/VM isolation | Docker containers inside Firecracker microVMs | Same isolation model proven by Fly.io; strong tenant isolation with fast boot times |
| Object storage | S3-compatible (metadata, logs, agent binaries, VM snapshots only — never user data) | Standard, swappable (AWS S3 or self-hosted MinIO) |
| Observability | Prometheus + Grafana + OpenTelemetry | Industry-standard, self-hostable, integrates natively via `prometheus-client` and the OpenTelemetry Python SDK |
| Payments | Razorpay Route + Cashfree Easy Split, behind a Payment Provider Abstraction Layer | Marketplace split-payment primitives (developer → platform → host payout) native to both providers |
| Container registry | Self-hosted OCI-compliant registry (for base OS images, CUDA images) | Avoids third-party rate limits for high-frequency image pulls at instance boot |
| Deployment | Kubernetes (control plane, gateway, API) + Terraform (infra-as-code) | Standard control-plane orchestration; Host Agent explicitly does **not** run in Kubernetes — it runs directly on host machines |

---

## 4. System Components (Detailed Responsibilities)

| Component | Runs where | Responsibilities |
|---|---|---|
| **Website** | Browser | Signup/login, browse marketplace, configure machine (GPU/CPU/RAM/storage/OS/region), pay, launch, view `kynetic connect` command, billing/usage dashboards, host dashboard |
| **API / Control Plane** | Kubernetes | Auth, marketplace listings, scheduler, billing/ledger, instance registry (source of truth for instance state), reputation, notification dispatch |
| **Tunnel Gateway** | Kubernetes (stateful set, region-local) | Session brokering between CLI and Host Agent, PTY multiplexing, port-forward multiplexing, file-transfer stream multiplexing, connection resilience/reconnect |
| **Host Agent** | Every rented machine | Hardware discovery, heartbeat, provisioning, Docker/Firecracker lifecycle, telemetry, PTY allocation, secure comms to Gateway, auto-update, crash recovery, resource cleanup, secure deletion |
| **kynetic CLI** | Developer's own machine | Auth, instance lifecycle commands, interactive session, file copy, port tunneling, config management |
| **Scheduler** | Control Plane | Ranks and selects a host for a launch request from price, GPU performance, host reputation, latency, availability, and reliability |
| **Billing Service** | Control Plane | Wallet, metering, ledger, invoices, payouts, refunds, payment-provider abstraction |
| **Postgres** | Managed / self-hosted cluster | Durable system of record |
| **Redis** | Managed / self-hosted cluster | Cache, pub-sub, queues, ephemeral scheduler state |

---

## 5. Cloud Computer Runtime

This is what happens **after** `kynetic connect` — the part of the system that must feel indistinguishable from a developer's own Linux box.

### 5.1 Launch-Time Provisioning Sequence

1. Control Plane's Scheduler selects a Host (see §9) and sends a `ProvisionInstance` RPC to that Host's Agent over the already-open Gateway-relayed stream.
2. Host Agent pulls the requested base OS image (Ubuntu LTS, versioned) from the self-hosted OCI registry if not already cached locally — image layers are cached per-host so repeat launches on the same machine are near-instant.
3. Host Agent allocates a **Firecracker microVM** with the requested CPU core count, RAM, and (if requested) GPU passthrough, and boots the OS image inside it.
4. Inside the microVM, a minimal init sequence brings up: networking (outbound-only NAT'd through the host, see §5.4), `sshd` bound to `localhost` only (never exposed publicly — reachable exclusively through the Gateway-relayed PTY channel), Docker daemon, and — if the instance was requested with GPU — the NVIDIA driver and CUDA/cuDNN runtime matched to the GPU model detected during host benchmarking.
5. Host Agent formats and mounts an **ephemeral NVMe-backed workspace volume** at a fixed path (`/workspace`), scoped to this instance's lifetime only.
6. Host Agent reports `instance.status = running` to the Control Plane; Control Plane updates the Instance Registry and the website's dashboard renders the `kynetic connect <INSTANCE_ID>` command.
7. Total target time from "Launch" click to `running`: under 60 seconds for a cached image on a healthy host (matches the "instant" bar set by Fly.io/Codespaces).

### 5.2 What Is Pre-Installed

Every instance boots with, at minimum: Ubuntu LTS base, Docker Engine, NVIDIA drivers + CUDA + cuDNN (GPU instances only), `git`, `curl`, `wget`, `tmux`, `screen`, build-essential toolchain, Python 3 + `pip`, Node.js + `npm`, and OpenSSH client/server. This list is intentionally minimal and general-purpose — Kynetic never pre-installs workload-specific tooling (no bundled ComfyUI, no bundled training frameworks); the developer installs whatever their workload needs, exactly as they would on their own machine.

### 5.3 Persistent vs. Ephemeral Storage

- **`/workspace`** — ephemeral, NVMe-backed, exists for the instance's lifetime, destroyed and cryptographically shredded on termination. This is where the developer's active work lives.
- **Optional persistent volume** (post-MVP extension point, see §20) — an explicitly-requested, separately-billed block volume that survives `stop`/`start` cycles but not `terminate`. Not required for MVP since Kynetic's philosophy is "pull data from the internet, don't accumulate state on the platform," but the schema (§12) reserves a `volumes` table for it.
- **Nothing is backed up by Kynetic.** This is a stated product principle, not a gap — the developer owns data durability by pulling from origin sources and pushing results back out (git remote, S3, HF Hub, etc.).

### 5.4 Networking Inside the Instance

- The microVM gets a private, host-local IP and reaches the public internet via NAT through the Host Agent's network namespace — full outbound internet access (so `git clone`, `curl`, `pip install`, `huggingface-cli download` all work exactly as on a normal machine).
- No inbound public exposure exists by default. If a developer wants to expose a service (e.g., a game server, a web app they're building) they use `kynetic tunnel` (§7) to request a Gateway-brokered public endpoint — explicit and revocable, never automatic.
- Per-instance network namespace with a default-deny **outbound** policy is *not* applied here (developers need arbitrary outbound internet access, unlike the isolation model of a locked-down CI job) — the isolation goal for compute rental is tenant/host protection (§14), not restricting developer internet use.

### 5.5 Shutdown, Cleanup, and Secure Deletion

- `stop`: microVM is paused/suspended; billing pauses; `/workspace` is retained on the host's disk in a stopped-instance-scoped area so `start` can resume quickly (subject to a configurable retention window before the host is allowed to reclaim disk space, see §17 state machine).
- `terminate`: microVM is destroyed; the ephemeral `/workspace` volume is cryptographically shredded (encryption-key destruction, not just filesystem delete) by the Host Agent, which reports a signed `deletion_receipt` back to the Control Plane before the instance is marked `terminated` — this receipt is a hard gate, mirrored from the security requirement that no residual data must be recoverable.
- Host Agent releases the Firecracker microVM's CPU/RAM/GPU allocation back into the host's available-resource pool and re-publishes availability to the Scheduler.

---

## 6. CLI Architecture

### 6.1 Design Principles

- **Single-file executable**, built with PyInstaller so the developer never needs a local Python interpreter or dependency install, distributed via a signed installer script and package managers (Homebrew, apt, a Windows installer) for discoverability, with a built-in `kynetic update` self-updater.
- **Sub-second cold start** — command dispatch happens before any network call where possible (e.g., `kynetic --help` never touches the network).
- **Config lives in a single local file** (`~/.kynetic/config`) storing the authenticated session token, default region/OS preferences, and known instance aliases — analogous to `~/.aws/config` or Tailscale's local state file.
- **Every long-running command is interruptible and resumable** — `Ctrl+C` on `kynetic connect` cleanly tears down the local PTY bridge without killing the remote session (the remote `tmux`/shell session the developer was in survives, exactly like real SSH + tmux behavior).

### 6.2 Command Reference

| Command | Purpose | Implementation notes |
|---|---|---|
| `kynetic login` | Authenticates the CLI to the Control Plane | Opens the system browser to a device-authorization flow (OAuth 2.0 Device Authorization Grant); CLI polls the Control Plane until the browser-side login completes, then stores a long-lived refresh token locally, encrypted with an OS-keychain-backed key where available |
| `kynetic launch` | Launches a machine from the CLI (mirrors the website flow) | Accepts flags for GPU type, CPU, RAM, storage, OS, region, and optional `--budget`/`--fastest` scheduler hints (see §9); calls the Control Plane launch RPC; prints the resulting `INSTANCE_ID` and the ready-to-run `kynetic connect` command |
| `kynetic connect <ID>` | Opens an interactive PTY session on the running instance | Dials the Tunnel Gateway over QUIC, authenticates with the CLI's session token, requests a PTY-session stream keyed by `INSTANCE_ID`; the Gateway splices this to the Host Agent's already-open stream for that instance; local terminal is put into raw mode and becomes a transparent pipe to the remote shell |
| `kynetic stop <ID>` | Suspends an instance | RPC to Control Plane → forwarded to Host Agent; billing pauses on confirmed `stopped` state |
| `kynetic terminate <ID>` | Destroys an instance permanently | RPC to Control Plane; requires the secure-deletion receipt before the CLI reports success, so the developer has a definitive "your data is gone" confirmation |
| `kynetic ls` | Lists the developer's instances | Reads from the Control Plane's Instance Registry (cached in Redis for low latency); shows ID, status, resource spec, region, uptime, running cost |
| `kynetic status <ID>` | Shows live health/telemetry for one instance | Streams a snapshot of CPU/GPU/RAM/disk/network utilization pulled from the Host Agent's telemetry stream, relayed through the Gateway |
| `kynetic logs <ID>` | Tails Host-Agent-level provisioning/system logs (not application logs — the developer's own processes are not captured or stored by Kynetic) | Streams from a bounded ring buffer the Host Agent keeps for boot/provisioning/health events only |
| `kynetic cp <src> <dst>` | Copies files to/from a running instance | Opens a dedicated file-transfer stream over the same Gateway-brokered session, using a chunked, resumable transfer protocol (see §7.5) |
| `kynetic tunnel <ID> <port>` | Exposes a local or remote port through the Gateway | Local mode: forwards a port on the instance to the developer's own machine (e.g., access a Jupyter/web UI running on the instance from `localhost`); public mode (`--public`): requests a Gateway-issued public endpoint for the port, explicit and revocable |
| `kynetic update` | Self-updates the CLI binary | Checks a version manifest served by the Control Plane's release channel, downloads and atomically replaces the binary, verifying a signature before installation |
| `kynetic config` | Views/edits local CLI configuration | Pure local file operation, no network call required for reads |

### 6.3 VS Code Remote SSH Support

`kynetic connect` also writes/updates a standard SSH-compatible host entry in the developer's `~/.ssh/config`, pointing at `localhost` on a locally-bound port that the CLI keeps open as a transparent proxy into the Gateway-brokered session for that instance (a local SSH-protocol-compatible listener, not a real public SSH endpoint). This means:

- VS Code's "Remote - SSH" extension, `scp`, `rsync`, and any other SSH-based tool work against the instance **without any change to those tools** — they connect to `localhost:<local-port>`, and the CLI's background proxy process tunnels the traffic through the same Gateway session used by `kynetic connect`.
- This local SSH-compatible proxy is started automatically the first time `kynetic connect` is run for an instance and torn down when the instance is stopped/terminated, or explicitly via a `--no-ssh-proxy` flag for developers who only want the raw PTY session.

### 6.4 Session Recovery

If the developer's network drops mid-session (laptop sleeps, wifi flaps), the CLI detects the stream failure, automatically re-dials the Gateway with the same session identity, and reattaches to the same PTY channel — combined with the developer running their shell inside `tmux`/`screen` (recommended, documented as the default onboarding tip), this makes the experience effectively continuous even across network interruptions, matching the resilience bar of `mosh` or a well-configured SSH client.

---

## 7. Tunnel Gateway (Connection Architecture)

This is the component that eliminates SSH-key distribution, public IPs, and NAT configuration as developer or host concerns.

### 7.1 Why Reverse-Dial Relay (and Not Direct P2P) for MVP

Consumer host machines (gaming PCs on home ISPs) are almost always behind NAT with no port-forwarding configured and no willingness from the host to configure one — this is explicitly a target host persona. A relay-based architecture where **both sides dial out** to a Gateway they both trust is the only approach that works unconditionally on day one, with zero host-side network configuration. This mirrors the pragmatic choice made by Cloudflare Tunnel and is the fallback path even in P2P-capable systems like Tailscale — Kynetic ships the fallback path only for MVP and reserves direct P2P as a documented future optimization (§20).

### 7.2 Session Establishment Sequence

```
Host Agent                    Tunnel Gateway                     kynetic CLI
    │                               │                                  │
    │──(1) mTLS dial, register─────▶│                                  │
    │      instance_id, host_id      │                                  │
    │◄─(2) ack, session held open───│                                  │
    │        (heartbeat every Ns)    │                                  │
    │                               │◄──(3) mTLS dial, request session──│
    │                               │      for instance_id               │
    │                               │──(4) authz check vs Control Plane─▶│
    │                               │◄─(5) authz OK──────────────────────│
    │◄─(6) "open PTY channel"───────│                                  │
    │──(7) PTY stream ready────────▶│                                  │
    │                               │══(8) splice CLI stream ⇄ Agent stream══│
    │◄════════════ full-duplex, multiplexed data flow ═════════════════▶│
```

- Step (1): the Host Agent's dial happens once, at instance boot, and is held open for the instance's entire lifetime (with automatic reconnect on transient network loss).
- Step (3): each `kynetic connect`, `kynetic cp`, `kynetic tunnel`, and `kynetic status` invocation opens its own logical **stream** multiplexed over the CLI's single Gateway connection — a developer can run `kynetic status` in one terminal while `kynetic connect` is active in another, sharing one underlying QUIC connection.
- Step (4): every session request is authorized against the Control Plane (does this CLI's authenticated user own/rent this instance, is the instance in a connectable state) before the Gateway will splice streams — the Gateway itself holds no authorization logic beyond "did the Control Plane say yes."

### 7.3 Multiplexing Model

A single Host Agent ↔ Gateway connection carries multiple independent logical streams simultaneously, distinguished by a stream-type + session-ID header on each multiplexed frame:

- **PTY stream** — interactive shell session (`kynetic connect`)
- **File-transfer stream** — chunked `kynetic cp` transfers
- **Telemetry stream** — periodic CPU/GPU/RAM/disk/network snapshots for `kynetic status` and the web dashboard
- **Control stream** — lifecycle RPCs (provision, stop, terminate, health-check)
- **Port-forward stream(s)** — one per active `kynetic tunnel`

This avoids opening a new TCP/QUIC connection per feature, keeping NAT/firewall traversal a one-time cost per instance and per CLI session.

### 7.4 Persistent Connections, Reconnect, and Session Recovery

- Both Host Agent and CLI send **keepalive heartbeats** on their Gateway connection; the Gateway considers a connection dead after a bounded number of missed heartbeats and immediately notifies the Control Plane (Host Agent side: triggers a host-availability downgrade in the Scheduler; CLI side: nothing, since the developer's own machine sleeping is not a host reliability signal).
- On reconnect, the Host Agent re-registers with its existing `instance_id`/`host_id` identity; any streams that were mid-flight (e.g., a `kynetic cp` transfer) resume from their last acknowledged byte offset (chunked transfer protocol carries resumability by design, §7.5).
- PTY sessions are **not** tied to the underlying transport connection's lifetime — the actual shell process lives inside the microVM and keeps running regardless of Gateway connectivity; the Gateway/CLI reconnect simply re-attaches to the still-running shell, which is why pairing with `tmux`/`screen` inside the instance yields true session persistence across the developer's own network drops.

### 7.5 File Transfer Protocol (`kynetic cp`)

Chunked, checksum-verified, resumable transfer over the multiplexed file-transfer stream: files are split into fixed-size chunks, each acknowledged individually; on reconnect, the CLI queries the last acknowledged chunk offset and resumes rather than restarting — this is a deliberate, purpose-built protocol rather than repurposing `scp`/`rsync` directly, so it can share the Gateway's session/auth model instead of requiring a separate SSH handshake (the SSH-compatible local proxy described in §6.3 remains available for developers who prefer `rsync`/`scp` semantics).

### 7.6 Gateway Statefulness and Regionality

- The Tunnel Gateway is deployed **region-local** (one Gateway cluster per supported region) so that both a host machine and the developer connecting to it take the shortest possible network path to a broker — the Gateway never needs to be in the same region as the Control Plane, only reachable from both the host and the CLI with low latency.
- Gateway instances are **horizontally scalable and stateless from a global perspective** — each holds only the live sessions it is actively brokering; instance/session assignment to a specific Gateway node is tracked in Redis so the Control Plane can route a `kynetic connect` request to the correct Gateway node holding that instance's Host Agent connection.

---

## 8. Host Agent

The Host Agent is the single piece of Kynetic software that runs on a stranger's machine. It must be minimal, auditable, self-healing, and trustworthy enough that a host is comfortable letting it run 24/7.

### 8.1 Internal Modules

| Module | Responsibility |
|---|---|
| **Discovery Module** | Enumerates CPU (core count, model), RAM (capacity, speed), storage (type — NVMe/SSD/HDD, capacity), and GPU (model, VRAM, driver version) at agent startup and on-demand; cross-checks GPU/CPU identifiers against a known-hardware-signature table to catch spoofed specs |
| **Benchmark Module** | Runs a standardized micro-benchmark suite (LLM inference throughput, raw compute FLOPs, disk I/O throughput) at onboarding and on a recurring schedule, reporting signed results to the Control Plane |
| **Heartbeat Module** | Sends a lightweight liveness + status ping (idle/busy/offline, temperature, power draw) to the Control Plane on a fixed interval over the Gateway control stream |
| **Provisioning Module** | Receives `ProvisionInstance`/`StopInstance`/`TerminateInstance` RPCs and drives the Docker/Firecracker lifecycle described in §5 |
| **Docker/Firecracker Lifecycle Manager** | Creates, pauses, resumes, and destroys microVMs; manages local OCI image cache; enforces per-instance CPU/RAM/GPU resource limits (cgroups-backed) so one tenant's instance cannot starve another's on a multi-tenant host |
| **Telemetry Module** | Continuously samples per-instance CPU/GPU/RAM/disk/network utilization and streams snapshots for `kynetic status` and host-side monitoring |
| **PTY Allocation Module** | On a Gateway-relayed "open PTY channel" request, spawns (or re-attaches to) a shell process inside the target microVM and bridges its stdio to the multiplexed stream |
| **Secure Comms Module** | Owns the Agent's mTLS client identity (certificate issued at host-registration time), all outbound Gateway/Control-Plane connections, and certificate rotation |
| **Auto-Update Module** | Periodically checks a signed release manifest; downloads and atomically swaps its own binary during an idle window (never mid-instance-provisioning), verifying signature before executing |
| **Crash Recovery Module** | A lightweight supervisor process (separate from the main Agent binary) restarts the Agent if it crashes, and on restart, the Agent reconciles its in-memory state against the Control Plane's view of "what instances should be running on this host" before resuming normal operation — no orphaned microVMs, no double-provisioning |
| **Resource Cleanup Module** | Enforces the secure-deletion sequence (§5.5) and reclaims freed CPU/RAM/GPU/disk into the host's available-resource pool, re-publishing availability to the Scheduler |
| **Scheduling Integration Module** | Reports current available capacity (free CPU/RAM/GPU/storage) to the Control Plane's Scheduler on every heartbeat, so the Scheduler always has a near-real-time view of what each host can accept |

### 8.2 Communication Model

- The Agent speaks exactly one protocol outward: mTLS-secured gRPC streaming to the Tunnel Gateway (control-plane RPCs are themselves relayed through the same Gateway connection rather than requiring a second direct link to the Control Plane API — this keeps the Agent's network footprint to a single outbound destination, simplifying host-side firewall reasoning to "one allowed outbound connection").
- The Agent never listens on any public-facing port. `sshd` inside the microVM binds to a private, host-internal address only — the Gateway relay is the only path in.

### 8.3 Trust Boundary

The Agent runs with the minimum host OS privileges required to manage Docker/Firecracker (documented as requiring a dedicated service account, not full root where the host OS packaging allows privilege separation for the virtualization stack). The Agent binary is code-signed; hosts can verify the signature of what they installed. Auto-update always re-verifies signature before swap, so a compromised release pipeline cannot silently push unsigned code to host machines.

---

## 9. Scheduler

### 9.1 Inputs

For every launch request, the Scheduler evaluates the pool of hosts whose currently-reported free capacity (from the Host Agent's Scheduling Integration Module) satisfies the requested spec (GPU model/VRAM, CPU cores, RAM, storage, region), then ranks candidates on:

| Signal | Source | Notes |
|---|---|---|
| Price | Listing price (host-set or auto-priced) | Lower is better, weighted by developer's stated priority (`--budget` vs `--fastest`) |
| GPU/CPU performance | Benchmark Module's most recent signed score | Normalized per hardware class |
| Host reputation | Composite reputation score (uptime, job success rate, past reliability) | See §10.5 |
| Latency | Estimated network path quality between the developer's likely region and the host's region (proxied by declared/verified host region, refined post-connect by observed Gateway RTT) | Only used as a tiebreaker for MVP — full latency-aware routing is a post-MVP refinement |
| Availability | Live free-capacity report from heartbeat | Hard filter, not just a ranking signal — a host reporting insufficient free capacity is excluded outright |
| Reliability/Health | Recent heartbeat consistency, thermal/power anomalies | Hosts with degraded recent health are down-ranked or excluded |

### 9.2 Ranking Algorithm (MVP: Deterministic Weighted Scoring)

A weighted linear score is computed per eligible host: `score = w1·price_score + w2·perf_score + w3·reputation_score + w4·availability_score − penalty(recent_failures)`, with weights tunable per the developer's stated intent (price-weighted for `--budget`, performance-weighted for `--fastest`, balanced by default). This mirrors the explicit MVP-first, evolve-to-ML-later approach used for the AI Router in the broader platform design — rule-based and fully explainable at launch, with the door open to a learned ranking model once enough completed-job outcome data exists.

### 9.3 Fallbacks

If zero hosts satisfy the requested spec in the requested region, the Scheduler offers the nearest satisfiable alternative (next-closest region, or a slightly different but compatible GPU class) rather than a hard failure, surfaced to the developer as an explicit choice at launch time (CLI and website both support "no exact match — did you mean X?").

### 9.4 Anti-Starvation

To prevent a small number of high-reputation, well-priced hosts from monopolizing all launch traffic (starving newer/lower-traffic hosts of any utilization, which would also starve them of the job history needed to build reputation), the Scheduler applies a bounded randomization factor within a top-N score band — candidates within a configurable score delta of the top pick are selected via weighted random choice rather than always picking the single highest-scoring host deterministically.

### 9.5 Rebalancing

The Scheduler does not proactively migrate running instances between hosts (migrating a live microVM mid-job is out of scope for MVP and conflicts with "feels like your own computer" — a real computer doesn't randomly move). Rebalancing is limited to **future launch decisions**: as reputation and availability data shifts, subsequent launches naturally redistribute load without disrupting any already-running instance.

---

## 10. Marketplace

### 10.1 Developer Workflow

Browse/filter listings (by GPU model, CPU/RAM/storage bundle, price, region, reputation) → select or let the Scheduler auto-select via budget/goal input → pay → launch → receive `kynetic connect` command. Manual browse and Scheduler-assisted selection are both first-class; neither is hidden behind the other.

### 10.2 Host Workflow

Install Host Agent → hardware auto-detected and benchmarked → listing auto-drafted from detected specs with a suggested price → host reviews/edits/accepts → listing goes live once verification passes → host dashboard shows utilization, earnings, and health.

### 10.3 Listings

A listing is a **resource bundle**, not a single-attribute (GPU-only) record: GPU model + VRAM (optional — CPU-only listings are valid), CPU core count, RAM, storage type/capacity, region, price per unit time, and current live availability state (derived from the Host Agent's heartbeat, not manually toggled by the host).

### 10.4 Machine Lifecycle (Marketplace-Level, Distinct From Instance Lifecycle)

A listing itself moves through `draft → pending_verification → active → paused (host-initiated) → delisted`. This is distinct from a rented **instance's** lifecycle (§17), which is per-rental, not per-listing — one listing produces many sequential instances over its lifetime as different developers rent the same underlying machine at different times.

### 10.5 Host Reputation

Composite score from: uptime (heartbeat consistency over a trailing window), job success rate (fraction of rentals that completed without host-side failure), average provisioning latency, and benchmark stability (does the machine's benchmark score stay consistent over time, or degrade/fluctuate suspiciously). Computed as a transparent, explainable weighted formula (not an opaque model) so hosts can understand and improve their score, recalculated after every completed rental.

### 10.6 GPU Benchmarks

Standardized suite (§8.1 Benchmark Module) run at onboarding and on a recurring schedule; results are the objective performance signal the Scheduler and the marketplace search/filter both rely on, replacing "trust the host's self-reported spec sheet" with "trust a measured, repeatable score."

### 10.7 Search, Filters, Regions

Marketplace search supports filtering by resource type/spec, price range, region, and reputation threshold, backed by a Postgres query against the `listings` table joined with the latest `reputation_scores` and `benchmarks`, with a Redis-cached view of currently-available listings to keep high-frequency browse traffic off the primary database's write path.

### 10.8 Machine Ownership

A listing is always owned by exactly one host account; a rented instance is always owned by exactly one developer account for its rental duration. There is no shared/multi-tenant occupancy of a single instance — one instance, one renter, matching "feels like your own computer."

---

## 11. Billing

### 11.1 Metering Model

Usage is metered by the Host Agent's Telemetry Module reporting **instance-seconds** of actual running time (not scheduled/reserved time) to the Billing Service over the Gateway control stream; the Billing Service aggregates these into billing periods and supports both **per-second** and **per-minute** billing granularity depending on the listing's configured rate unit (per-second is the default and the product-preferred granularity; per-minute exists for listing types where sub-minute metering doesn't make sense, e.g., a flat-rate storage-only listing).

### 11.2 Wallet

Every developer account has a wallet (multi-currency capable, INR/USD at minimum) auto-created at signup. Launching an instance places a **hold** for an estimated cost ceiling; actual metered usage debits the wallet incrementally in near-real-time; the hold is released/reconciled against actual usage on `stop`/`terminate`. A zero-balance wallet triggers automatic instance suspension.

### 11.3 Marketplace Payments and Host Payouts

Every transaction is a **split payment**: developer pays the listed rate; platform commission is deducted; the remainder accrues to the host's payout balance. This is implemented via the Payment Provider Abstraction Layer's split-payment primitives rather than Kynetic manually moving money between accounts post-hoc — using **Razorpay Route** and **Cashfree Easy Split**, both of which natively support marketplace-style split settlement (funds are routed to the host's linked payout account automatically at settlement time, with the platform commission retained).

### 11.4 Payment Provider Abstraction Layer

A single internal interface (`charge`, `refund`, `split_settle`, `payout`, `webhook_handle`) is implemented once per provider (Razorpay Route adapter, Cashfree Easy Split adapter) so the rest of the Billing Service never branches on which provider is active — provider selection is a routing decision (e.g., by region or by account preference), not a code fork. This also means a third provider can be added later by implementing the same interface, with zero change to the ledger or metering logic.

### 11.5 Ledger

A single **append-only ledger table** (§12) is the ultimate source of truth for every credit/debit/hold/release/refund/payout/commission event — the wallet balance itself is a derived, cached value, always reconstructable by replaying the ledger. This is a deliberate accounting-correctness choice: balances are never mutated directly, only ever the result of a new ledger entry.

### 11.6 Refunds

Refunds are modeled as a ledger entry type (`refund`), always referencing the original transaction they reverse, and always routed back through the same Payment Provider Abstraction Layer so provider-side refund APIs (which have their own settlement timing) are respected rather than Kynetic pretending a refund is instantaneous when the underlying rail isn't.

### 11.7 Invoices and Settlement

Invoices are generated per billing period (or per completed rental, whichever the region's compliance needs require) from the ledger, not recomputed from raw metering events — this guarantees an invoice always reconciles exactly against the ledger. Host settlement (payout) runs on a scheduled cadence (e.g., daily/weekly, configurable), batching all `payout`-eligible ledger entries since the last settlement run through the active Payment Provider adapter.

---

## 12. Database Design (PostgreSQL)

### 12.1 Core Tables

**Identity & Access**
- `accounts` (id, email, auth_provider, role[host|developer|both], created_at)
- `sessions` (id, account_id, device_info, created_at, expires_at) — backs CLI device-auth sessions
- `api_credentials` (account_id, hashed_secret, scopes, created_at)

**Hosts & Hardware**
- `hosts` (id, account_id, status[pending_verification|verified|suspended], agent_version, mtls_cert_fingerprint, region, created_at)
- `host_hardware` (host_id, cpu_model, cpu_cores, ram_gb, storage_type, storage_gb, gpu_model, gpu_vram_gb, driver_version, reported_at)
- `host_benchmarks` (id, host_id, benchmark_type, score, raw_metrics_json, run_at)
- `host_heartbeats` (host_id, status[idle|busy|offline], free_cpu, free_ram_gb, free_gpu, temperature_c, power_draw_w, recorded_at)
- `reputation_scores` (id, host_id, uptime_score, job_success_score, benchmark_stability_score, composite_score, computed_at)

**Marketplace**
- `listings` (id, host_id, gpu_model, gpu_vram_gb, cpu_cores, ram_gb, storage_type, storage_gb, region, price_amount, price_currency, price_unit[second|minute], status[draft|pending_verification|active|paused|delisted], created_at)

**Instances**
- `instances` (id, developer_id, listing_id, host_id, status, region, connect_token_hash, started_at, stopped_at, terminated_at, billed_seconds)
- `instance_events` (id, instance_id, event_type, metadata_json, occurred_at) — provisioning/lifecycle event trail, backs `kynetic logs`
- `deletion_receipts` (instance_id, verified_at, method, signed_by_host_cert)
- `volumes` (id, instance_id nullable, developer_id, size_gb, status, created_at) — reserved for the post-MVP persistent-volume extension point

**Billing**
- `wallets` (id, account_id, balance_inr, balance_usd, preferred_currency, updated_at) — derived/cached from `ledger_entries`
- `ledger_entries` (id, account_id, instance_id nullable, type[hold|debit|release|refund|payout|commission], amount, currency, reference_id, created_at) — append-only
- `invoices` (id, account_id, period_start, period_end, total_amount, currency, pdf_url, issued_at)
- `payout_accounts` (host_id, provider[razorpay|cashfree], provider_account_id, status)
- `payout_batches` (id, host_id, amount, currency, provider, status, settled_at)

**Security & Ops**
- `audit_logs` (id, actor_id, action, resource_type, resource_id, metadata_json, created_at) — append-only
- `security_events` (id, event_type, severity, resource_type, resource_id, details_json, created_at)
- `device_fingerprints` (account_id, fingerprint_hash, first_seen, last_seen)
- `trust_tiers` (account_id, tier, spend_cap, gpu_hour_cap, updated_at)

### 12.2 Key Relationships (ER Summary)

```
accounts 1─┬─* hosts               accounts 1─┬─* instances (as developer)
           └─* wallets                          └─* sessions
hosts 1─┬─* host_hardware          listings 1─* instances
        ├─* host_benchmarks        instances 1─┬─* instance_events
        ├─* host_heartbeats                     ├─1 deletion_receipts
        ├─* reputation_scores                   └─* volumes (optional)
        └─* listings
accounts 1─* ledger_entries ──(instance_id nullable)──▶ instances
hosts 1─* payout_accounts ─* payout_batches
```

### 12.3 Indexing Strategy

- `listings`: composite index on `(status, region, gpu_model)` for marketplace filter queries; index on `(host_id)` for host-dashboard lookups.
- `instances`: index on `(developer_id, status)` for `kynetic ls`; index on `(host_id, status)` for host-side utilization queries.
- `host_heartbeats`: index on `(host_id, recorded_at DESC)` — this table is high-write-volume and should be partitioned by time (e.g., monthly partitions) with an aggressive retention/rollup policy, keeping only recent raw heartbeats and rolling up historical uptime into `reputation_scores`.
- `ledger_entries`: index on `(account_id, created_at)` and `(instance_id)` — append-only, never updated, so index maintenance cost is write-only, no update churn.
- `audit_logs` / `security_events`: index on `(resource_type, resource_id, created_at)` for incident investigation queries.

---

## 13. API Design

### 13.1 Principles

- **External surface: REST/JSON** over HTTPS for the website and any third-party integration; **internal surface: gRPC** between Control Plane, Gateway, and Host Agent for performance and strong typing; the CLI talks gRPC directly to the Gateway (not REST) for the connect/session-management paths, and REST to the Control Plane for lifecycle/billing/marketplace operations that don't need streaming.
- **Versioning** via a URL path prefix (`/v1/...`) for REST; gRPC services versioned via package namespace (`kynetic.v1.*`), allowing internal protocol evolution without breaking the CLI's compatibility contract (CLI itself declares a minimum-supported API version at `kynetic login` time and prompts `kynetic update` if too old).
- **Authentication**: every REST call carries a bearer JWT (short-lived access token + refresh token issued at `kynetic login`/website login); every gRPC call (CLI↔Gateway, Agent↔Gateway) is additionally wrapped in mTLS at the transport layer.
- **Authorization**: resource-scoped checks on every call (does this account own/rent this instance, is this host account authorized to manage this listing) — centralized in a shared authz middleware, not duplicated per-handler.
- **Idempotency**: all state-mutating REST endpoints (`launch`, `stop`, `terminate`, `topup`) accept an `Idempotency-Key` header; the Control Plane deduplicates retried requests within a bounded time window, which matters specifically because CLI commands over a flaky network are expected to retry.
- **Errors**: a consistent error envelope (`code`, `message`, `retryable: bool`) across every endpoint, so the CLI can make a single generic "should I retry" decision rather than special-casing per-endpoint error shapes.
- **Pagination**: cursor-based (not offset-based) for `kynetic ls`/marketplace listing endpoints, since offset pagination degrades under concurrent inserts into a live, fast-changing dataset.
- **WebSockets**: used by the **website** for live status/telemetry updates (instance status, host dashboard metrics) — a lighter-weight choice than gRPC-Web for browser clients.
- **gRPC**: used for all CLI↔Gateway and Gateway↔Host Agent traffic, where bidirectional streaming (PTY, telemetry, file transfer) is a first-class requirement, not an add-on.

### 13.2 Representative REST Endpoint Groups

```
# Auth
POST /v1/auth/device/start          → begins CLI device-authorization flow
POST /v1/auth/device/poll           → CLI polls for completed browser login
POST /v1/auth/refresh
GET  /v1/auth/me

# Marketplace
GET  /v1/listings                   → filterable, cursor-paginated
GET  /v1/listings/{id}
POST /v1/listings                   → host creates listing
PATCH /v1/listings/{id}

# Instances
POST /v1/instances                  → launch (Idempotency-Key required)
GET  /v1/instances                  → kynetic ls
GET  /v1/instances/{id}
POST /v1/instances/{id}/stop
POST /v1/instances/{id}/start
POST /v1/instances/{id}/terminate
GET  /v1/instances/{id}/events      → kynetic logs backing data

# Billing
GET  /v1/wallet
GET  /v1/wallet/ledger
POST /v1/wallet/topup
GET  /v1/invoices/{id}
POST /v1/payout-accounts

# Hosts
POST /v1/hosts/register
GET  /v1/hosts/{id}
GET  /v1/hosts/{id}/dashboard
GET  /v1/hosts/{id}/reputation

# Admin/Security
POST /v1/admin/kill-switch
GET  /v1/admin/security-events

GET  /healthz   (every service)
```

### 13.3 Representative gRPC Services

```
kynetic.v1.GatewaySessionService
  - OpenPTYSession(stream) returns (stream)
  - OpenFileTransfer(stream) returns (stream)
  - OpenPortForward(stream) returns (stream)
  - StreamTelemetry(request) returns (stream)

kynetic.v1.HostAgentControlService
  - RegisterAgent(request) returns (response)
  - Heartbeat(stream) returns (stream)
  - ProvisionInstance(request) returns (response)
  - StopInstance(request) returns (response)
  - TerminateInstance(request) returns (response)
  - ReportDeletionReceipt(request) returns (response)
```

---

## 14. Security

### 14.1 Identity & Access

- **JWT** (short-lived access + rotating refresh) for all REST/website sessions.
- **OAuth 2.0 Device Authorization Grant** for CLI login (`kynetic login`) — no password ever touches the CLI or gets typed into a terminal; the browser handles credential entry, the CLI only receives a token.
- **mTLS** for every Host Agent↔Gateway and Gateway↔Control-Plane connection — certificate issued at host-registration time, rotated on a fixed schedule by the Agent's Secure Comms Module.
- **RBAC**: `developer`, `host`, `admin` roles gate REST/gRPC endpoints; a single account can hold both `developer` and `host` roles simultaneously.

### 14.2 Session/Connection Security

- The **connect token** issued for `kynetic connect` (stored hashed in `instances.connect_token_hash`) is short-lived and scoped to exactly one instance — it is not a reusable credential, and it is invalidated the moment the instance is stopped or terminated.
- No SSH key is ever generated for or distributed to the developer for host access — the Gateway-brokered PTY channel replaces key-based SSH entirely for the core `connect` flow (the optional local SSH-compatible proxy in §6.3 rides on top of this same authenticated channel, it does not introduce a separate key-based trust path).

### 14.3 Secrets Management

Provider API keys (Razorpay, Cashfree), signing keys (Host Agent release signing, CLI release signing), and database credentials are held in a dedicated secrets manager (Kubernetes Secrets backed by an external KMS, or an equivalent managed secrets service) — never in source control, never in plain environment variables baked into container images.

### 14.4 Container/VM Isolation and Sandboxing

Every rented instance runs inside a Docker-container-in-Firecracker-microVM sandbox with no host filesystem access exposed to the workload, a scoped ephemeral storage volume, cgroup-enforced CPU/RAM/GPU limits, and secure/cryptographic deletion on termination (§5.5, §8.1) — this is the same isolation posture that lets Kynetic host arbitrary, untrusted developer code on arbitrary, untrusted host hardware safely in both directions.

### 14.5 Rate Limiting

Applied at the API Gateway layer (REST) and at the Tunnel Gateway (new-session-open rate per account) to blunt both scripted abuse of the marketplace/billing APIs and connection-flood attempts against the tunnel infrastructure.

### 14.6 Fraud Detection (MVP: Rule-Based)

Device fingerprinting at signup/login to catch multi-account abuse; wallet transaction pattern rules (rapid top-up + rapid spend, chargeback signals) evaluated as a scheduled job against `ledger_entries`; new accounts start at a restrictive `trust_tier` (capped spend/instance-size/GPU-hours) that unlocks progressively with account history.

### 14.7 Audit Logging

Every state-mutating action across every service writes an `audit_logs` row (actor, action, resource, metadata, timestamp); security-relevant events (failed auth, rate-limit trips, kill-switch activations) additionally write to `security_events`, kept logically separate from general audit trail per purpose-scoped logging discipline.

### 14.8 Encryption

TLS/mTLS in transit everywhere (no unencrypted internal traffic, even within the cluster); encryption at rest for the primary database and for the ephemeral instance workspace volumes (so a stolen/repurposed host disk after a shredded-but-imperfect deletion still yields nothing usable).

---

## 15. Observability

### 15.1 Metrics

`prometheus-client` instrumentation in every Python service (Control Plane, Gateway, and — critically — the Host Agent itself, which exposes a local metrics endpoint scraped indirectly via its telemetry stream since it cannot be scraped directly from outside the host's network). Key metric families: request latency/error-rate per RPC, active Gateway sessions, instance provisioning duration, heartbeat freshness per host, wallet ledger write throughput.

### 15.2 Tracing

`OpenTelemetry` spans propagated across the full request path — website/CLI → Control Plane → Gateway → Host Agent — so a slow `kynetic launch` or `kynetic connect` can be root-caused to a specific hop (scheduler decision latency vs. Gateway session setup vs. Host Agent provisioning) rather than treated as a black box.

### 15.3 Logging

Structured (JSON) logs from every service, correlated by a request/trace ID that flows through the same OpenTelemetry context, aggregated centrally for search — this is what backs `kynetic logs` at the provisioning/system-event level (never the developer's own application output, which Kynetic does not capture).

### 15.4 Dashboards and Alerts

`Grafana` dashboards for: platform-wide health (Gateway session counts, provisioning success rate, billing throughput), per-host health (for the host dashboard's temperature/utilization views), and on-call alerting (heartbeat staleness beyond threshold, provisioning failure rate spike, ledger reconciliation mismatch, Gateway connection error rate spike) routed to an incident channel/pager.

---

## 16. Deployment

### 16.1 Topology

- **Control Plane services** (Auth, Marketplace, Scheduler, Billing, Instance Registry): Kubernetes, horizontally scaled, deployed per-region with a primary region owning the authoritative Postgres cluster (read replicas in other regions for latency-sensitive reads like marketplace browse).
- **Tunnel Gateway**: Kubernetes, deployed **region-local**, one cluster per supported region, stateless-from-a-global-perspective (session-to-node assignment tracked in Redis, §7.6).
- **Host Agent**: runs directly on rented host machines — explicitly outside Kubernetes, since hosts are arbitrary third-party machines, not platform-managed infrastructure.
- **Database**: managed/self-hosted PostgreSQL cluster with automated backups and point-in-time recovery (backups cover platform metadata/billing/marketplace data only — never instance/workspace data, which is never persisted by the platform in the first place).
- **Redis**: managed/self-hosted cluster for cache, pub-sub, and scheduler working set, with persistence enabled for the queue/session-tracking use cases and disabled (pure cache) where appropriate.
- **Object storage**: S3-compatible, storing Host Agent/CLI release binaries, base OS/CUDA OCI images, and audit-log archival exports.
- **Container registry**: self-hosted OCI registry for base OS and CUDA images, geographically distributed/cached close to host machines to keep provisioning-time image pulls fast.

### 16.2 CI/CD

GitHub Actions pipelines: lint (`ruff`) + unit/integration tests (`pytest`/`pytest-asyncio`) + build on every PR for all Python services, the CLI, and the Host Agent; signed PyInstaller binary builds (CLI, Host Agent) published to the release channel on tag; container image builds pushed to the internal registry on merge to main; database migrations run as a gated, reviewed step (never auto-applied on every deploy without review, given the billing ledger's correctness requirements).

### 16.3 Autoscaling

Control Plane and Tunnel Gateway services scale horizontally on standard resource-utilization-based Kubernetes autoscaling; the Gateway additionally scales on **active session count** per node (a custom metric) since session-brokering load doesn't always correlate cleanly with CPU usage.

### 16.4 Disaster Recovery

- Database: automated backups + point-in-time recovery, tested restore drills on a fixed cadence.
- Gateway: stateless-enough that losing a Gateway node only drops the sessions it was actively brokering — affected CLIs and Host Agents reconnect automatically (§7.4) to a healthy node without manual intervention.
- Host Agent crash/host machine reboot: Crash Recovery Module (§8.1) reconciles state on restart; if a host machine is permanently lost, its in-flight instances are marked `failed` and the affected developer is notified and refunded for unused prepaid time via the ledger's `refund` entry type.

### 16.5 Global Regions

Each supported region has: a Tunnel Gateway cluster, a Postgres read replica (with the primary in one designated home region), and a local OCI image cache — new region rollout is templated via Terraform so adding a region is an infrastructure-as-code operation, not a bespoke engineering effort per region.

---

## 17. State Machines

### 17.1 Instance Lifecycle

```
        launch requested
              │
              ▼
        [ pending ]
              │  scheduler assigns host, provisioning RPC sent
              ▼
        [ provisioning ]──(provisioning failure)──▶ [ failed ] ──▶ refund via ledger
              │  Host Agent reports running
              ▼
        [ running ] ◄────────────────┐
         │        │                   │ start
         │ stop    │ terminate         │
         ▼        │                   │
   [ stopping ]    │              [ stopped ]
         │          │                   ▲
         ▼          │                   │
   [ stopped ] ──────┘── (retention window expiry, host reclaims disk)
                     │
                     ▼
              [ terminating ]
                     │  deletion receipt verified
                     ▼
              [ terminated ]
```

### 17.2 Host/Listing Lifecycle

```
   registered
      │  hardware detected + benchmark run
      ▼
 [ pending_verification ] ──(spec mismatch / benchmark failure)──▶ [ flagged ] ──▶ [ suspended ]
      │  verification passes
      ▼
   [ verified ] ──(host creates listing)──▶ listing: [ draft ] ──▶ [ pending_verification ]
      │                                                                   │
      │                                                          (image/listing checks pass)
      │                                                                   ▼
      │                                                             [ active ]
      │                                                              │      │
      │                                                        (host pauses) (host delists)
      │                                                              ▼      ▼
      │                                                         [ paused ] [ delisted ]
      ▼
 [ suspended ] (kill-switch or abuse detection)
```

### 17.3 Wallet/Ledger State (Conceptual, Not a Literal State Machine)

Since the ledger is append-only, "state" is always a **derived aggregate**, not a stored transition: `wallet.balance = SUM(ledger_entries WHERE account_id = X)`, recomputed/cached on every write and periodically reconciled in full as an integrity check (a scheduled job that recomputes every wallet balance from scratch and alerts on any drift from the cached value).

---

## 18. Sequence Diagrams

### 18.1 `kynetic launch` → `kynetic connect`

```
Developer      CLI            Control Plane        Scheduler       Host Agent      Tunnel Gateway
   │            │                    │                  │               │                │
   │─kynetic launch──▶│              │                  │               │                │
   │            │─POST /v1/instances─▶│                 │               │                │
   │            │                    │──rank hosts─────▶│               │                │
   │            │                    │◄──best host──────│               │                │
   │            │                    │──ProvisionInstance (via Gateway)──────────────────▶│
   │            │                    │                  │               │◄───relay────────│
   │            │                    │                  │               │─provision microVM
   │            │                    │◄──instance.running (via heartbeat)────────────────│
   │            │◄──INSTANCE_ID + connect command────────│               │                │
   │◄─prints "kynetic connect ID"────│                  │               │                │
   │            │                    │                  │               │                │
   │─kynetic connect ID──▶│          │                  │               │                │
   │            │──dial Gateway, request PTY session for ID──────────────────────────────▶│
   │            │                    │                  │               │◄──authz check──▶│ (Control Plane)
   │            │                    │                  │               │──open PTY───────▶│
   │            │◄══════════════ spliced PTY stream ══════════════════════════════════════│
   │◄─raw terminal, now == remote shell─│               │               │                │
```

### 18.2 `kynetic terminate` (Secure Deletion Path)

```
Developer   CLI        Control Plane      Tunnel Gateway     Host Agent
   │         │               │                  │                │
   │─terminate ID──▶│        │                  │                │
   │         │─POST /instances/{id}/terminate──▶│                │
   │         │               │──TerminateInstance (relayed)──────▶│
   │         │               │                  │                │─destroy microVM
   │         │               │                  │                │─shred workspace volume
   │         │               │                  │                │─sign deletion receipt
   │         │               │◄──ReportDeletionReceipt────────────│
   │         │               │─verify signature, write deletion_receipts row
   │         │◄──"terminated, data destroyed"────│                │
   │◄─CLI prints confirmation─│                  │                │
```

---

## 19. Failure Recovery

| Failure | Detection | Recovery |
|---|---|---|
| Host Agent crashes | Crash Recovery supervisor process misses agent liveness | Supervisor restarts Agent; Agent reconciles in-memory state against Control Plane's expected running-instances list on restart |
| Host machine loses power/network | Missed heartbeats beyond threshold | Control Plane marks host `offline`, in-flight instances marked `failed`, affected developers notified + refunded via ledger `refund` entries, host excluded from Scheduler until heartbeat resumes |
| Gateway node fails | Node health check fails / connections drop | Kubernetes reschedules the node; affected Host Agents and CLIs auto-reconnect (§7.4) to a healthy Gateway node in the region; PTY sessions reattach to the still-running remote shell process, which was never dependent on the Gateway node's lifetime |
| Developer's network drops mid-session | CLI detects stream failure | CLI auto-redials Gateway with same session identity; reattaches to the same still-running PTY (best experienced when the developer's remote shell is inside `tmux`/`screen`) |
| Database primary failure | Health check / replication lag alert | Failover to a standby/read-replica promoted to primary; Control Plane services reconnect via a standard connection-string failover mechanism |
| Payment provider outage | Payment Provider Abstraction Layer receives error/timeout from active provider | Charge/payout attempt marked `pending_retry`; scheduled retry with backoff; if a provider is down for an extended window, new transactions can be routed to the secondary provider adapter without any change to ledger semantics |
| Provisioning failure on selected host | Host Agent reports provisioning error, or provisioning RPC times out | Instance marked `failed`, held funds released via ledger, Scheduler immediately retries against the next-ranked candidate host (transparent retry, not surfaced as an error to the developer unless all candidates are exhausted) |
| Benchmark/spec mismatch discovered post-listing | Periodic re-benchmark job (§8.1) detects drift from registered specs | Listing auto-paused, host notified, reputation score penalized, manual re-verification required before relisting |

---

## 20. Scaling Strategy

- **Control Plane**: stateless services scale horizontally behind standard Kubernetes autoscaling; Postgres read replicas absorb marketplace-browse read load; write-heavy paths (ledger, heartbeats) are the primary scaling constraint and are addressed via table partitioning (heartbeats, by time) and append-only design (ledger — no update contention).
- **Tunnel Gateway**: scales horizontally per-region on active-session-count; regional deployment keeps any single Gateway cluster's session count bounded to its region's traffic rather than one global bottleneck.
- **Host fleet**: scaling the marketplace's supply side is purely a function of host onboarding funnel performance (§5, §8), not a backend scaling concern — the architecture imposes no artificial ceiling on host count since each Host Agent is an independent, self-contained node.
- **Hybrid overflow (explicit extension point, not MVP)**: when native host supply cannot satisfy demand for a given spec/region, the same Scheduler interface that ranks native hosts can be extended with an additional "provider adapter" abstraction that surfaces external cloud capacity (AWS/Azure/GCP/etc.) as if it were just another rankable host — deferred post-MVP, but the Scheduler's host-ranking interface is deliberately designed generically enough (score-based ranking over a pool of "capacity providers") to accommodate this without a rearchitecture.
- **Direct P2P connection upgrade (explicit extension point, not MVP)**: once the relay-only Gateway architecture (§7) is stable in production, a WireGuard-based opportunistic direct-connection upgrade (attempted after the relay session is already established, falling back silently to relay if P2P negotiation fails) can reduce Gateway bandwidth costs and latency for the subset of host/developer pairs where direct connectivity is possible — this is additive and does not change the CLI's or Host Agent's external contract.
- **Persistent volumes (explicit extension point, not MVP)**: the `volumes` table (§12.1) is reserved so that a future "keep my workspace across terminate, not just stop" feature can be added without a schema migration surprise, once there's demonstrated demand — not built at launch because it cuts against the "compute, not storage" principle unless explicitly opted into.

---

## 21. Engineering Roadmap

> Comprehensive phase-by-phase engineering roadmap for Kynetic AI, progressing from foundations through production launch: Foundations → Host Onboarding & Marketplace → Cloud Computer Runtime → Host Agent Completion → Connection Layer & CLI → Developer Experience → Marketplace & Payments → Production Hardening → Launch.

---

### PHASE A — Foundations

**Objectives:** Auth service (OAuth2 Device Authorization Grant flow), core DB schema (`users`, `sessions`, `api_tokens`, `events`, `device_codes`), and versioned API Gateway skeleton.

**Architecture:** Stateless Python/FastAPI microservices communicating with PostgreSQL system of record and Redis cache/pubsub. 100% Python CLI (`kynetic-cli`) using Click/Typer, Rich, HTTPX, Pydantic, keyring, and cryptography.

**Deliverables:** Working `kynetic login`, `kynetic logout`, `kynetic config`, `kynetic version`, device code grant flow (`POST /v1/auth/device/code`, `POST /v1/auth/device/token`, `POST /v1/auth/device/verify`), and authenticated CLI.

**Backend tasks:** Auth Service device code endpoints, JWT issuance/rotation, database migrations for core user/auth tables.

**CLI tasks:** `kynetic` executable built with Click/Rich/HTTPX/Pydantic, credential storage in `~/.kynetic/credentials`, version checking against API Gateway.

**Database migrations:** `users`, `sessions`, `api_tokens`, `events`, `device_codes`.

**Testing:** Unit and integration test suite for token issuance, device flow polling, and CLI authentication (`test_cli_auth.py`, `test_v6_phase_a_auth.py`).

**Acceptance criteria:** A developer can run `kynetic login` from a fresh terminal, complete authentication in the browser, and store a secure credential token locally.

---

### PHASE B — Host Onboarding & Marketplace

**Objectives:** Physical hardware discovery, mTLS host registration, repeatable benchmarking, and marketplace compute search/listings.

**Architecture:** Host Agent hardware discovery module (`hardware_detect.py`), benchmark runner (`benchmark_runner.py`), mTLS client certificate issuance, and Marketplace Service (`marketplace_service`).

**Deliverables:** Real host machines can register via `POST /v1/hosts/register`, receive X.509 mTLS certificates, submit FLOPS/LLM benchmarks, ingest live 10s heartbeats, and appear in `GET /v1/listings`.

**Backend tasks:** Host Service state machine (`pending_verification` → `benchmarking` → `verified`), internal CA mTLS client certificate issuer, Marketplace compute search endpoint with GPU/VRAM/price/region filtering.

**Host Agent tasks:** Hardware discovery module using `psutil`/`pynvml`, benchmark runner executing matrix mult FLOPS & LLM inference loops, HTTPX async client for registration and heartbeats.

**Database migrations:** `hosts`, `machines`, `gpus`, `cpu_specs`, `ram_specs`, `storage_specs`, `regions`, `listings`, `host_hardware_specs`, `host_benchmarks`, `host_heartbeats`.

**Testing:** Hardware detection mocks, benchmark verification test suite, marketplace search filtering test suite (`test_v6_phase_b_host_marketplace.py`).

**Acceptance criteria:** Physically different test machines register, pass benchmark verification, transition to `verified`, create active marketplace listings, and stream telemetry heartbeats.

---

### PHASE C — Cloud Computer Runtime Foundation

**Objectives:** Stand up the actual "rent a real Linux machine" capability — Host Agent core, Firecracker/Docker provisioning, base OS/CUDA image pipeline.

**Architecture:** Host Agent (Discovery, Provisioning, Docker/Firecracker Lifecycle Manager modules only at this stage) talking directly to the Control Plane over a temporary direct mTLS link (the full Gateway relay architecture lands in Phase E — this phase intentionally scopes down to prove the runtime works before building the connection layer around it).

**Deliverables:** A host machine can register, report hardware, and receive a `ProvisionInstance` RPC that results in a real, running, GPU-enabled (where applicable) Linux microVM with Docker/CUDA ready.

**Backend tasks:** Instance Registry service; Control Plane RPCs for provision/stop/terminate; base OCI image build pipeline (Ubuntu LTS + CUDA variants) and self-hosted registry.

**Frontend tasks:** None (out of scope for this phase — runtime-first, UI-later).

**CLI tasks:** None yet — CLI work begins in Phase D.

**Host Agent tasks:** Discovery Module, Provisioning Module, Docker/Firecracker Lifecycle Manager, local OCI image caching, ephemeral workspace volume allocation, secure-deletion sequence (§5.5).

**Database migrations:** `hosts`, `host_hardware`, `instances`, `instance_events`, `deletion_receipts`.

**Infrastructure:** Self-hosted OCI registry; Firecracker-capable host provisioning documentation/tooling for early test hosts.

**Testing:** Provision/stop/terminate correctness tests against real test hardware (at least one GPU host, one CPU-only host); secure-deletion verification test (confirm no residual data recoverable post-termination).

**Acceptance criteria:** A provisioned instance boots in under 60 seconds on a cached image; terminate produces a verified deletion receipt; a crashed Host Agent recovers to correct state on restart without orphaning a microVM.

**Dependencies:** Phases A/B (auth, base Control Plane, base DB).

**Risk:** High — Firecracker/GPU-passthrough correctness across heterogeneous consumer hardware is the riskiest technical bet in the entire platform.

**Complexity:** High.

**Estimated timeline:** 4–5 weeks.

---

### PHASE D — Host Agent Completion (Telemetry, Heartbeat, Benchmarking, Auto-Update)

**Objectives:** Complete the Host Agent into a self-sufficient, self-healing, continuously-verified daemon.

**Architecture:** Adds Heartbeat, Benchmark, Telemetry, Secure Comms, Auto-Update, and Crash Recovery modules to the Phase C runtime core.

**Deliverables:** A Host Agent that reports live status, passes a repeatable benchmark suite, re-verifies itself on a schedule, updates itself safely, and recovers from crashes without operator intervention.

**Backend tasks:** Heartbeat ingestion endpoint; benchmark result storage/verification; release-manifest service for Agent auto-update.

**Frontend tasks:** Minimal internal host-health view for engineering debugging only (not the full host dashboard, which lands in Phase H).

**CLI tasks:** None yet.

**Host Agent tasks:** Heartbeat Module, Benchmark Module (LLM inference / FLOPs / disk I/O suite), Secure Comms Module (mTLS cert issuance/rotation), Auto-Update Module (signed manifest check + atomic binary swap), Crash Recovery supervisor process + state reconciliation logic.

**Database migrations:** `host_heartbeats` (partitioned by time), `host_benchmarks`.

**Infrastructure:** Signed release pipeline for Agent binaries; heartbeat-ingestion scaling test (simulate hundreds of concurrent hosts).

**Testing:** Kill-and-recover chaos tests on the Agent process; benchmark repeatability tests (same hardware, same score within tolerance across runs); auto-update rollback test (corrupted/unsigned update is rejected).

**Acceptance criteria:** Heartbeat staleness beyond threshold correctly triggers a host-offline state within the Control Plane; benchmark re-run on a schedule detects a deliberately-degraded test host; Agent restarts cleanly after a forced crash with zero orphaned instances.

**Dependencies:** Phase C.

**Risk:** Medium.

**Complexity:** Medium-High.

**Estimated timeline:** 3 weeks.

---

### PHASE E — Tunnel Gateway & Connection Layer

**Objectives:** Build the reverse-dial relay architecture that eliminates SSH/NAT/public-IP concerns end-to-end.

**Architecture:** New Tunnel Gateway service (region-local, Kubernetes); Host Agent gains a Secure Comms path to the Gateway (replacing the temporary direct link from Phase C); session multiplexing protocol (PTY/file-transfer/telemetry/control/port-forward streams over one connection, §7.3).

**Deliverables:** A Host Agent can hold a persistent Gateway session; a test client can request and receive a spliced PTY stream to a running instance.

**Backend tasks:** `GatewaySessionService` and `HostAgentControlService` gRPC definitions and implementation; session-to-Gateway-node tracking in Redis; authz check integration between Gateway and Control Plane (§7.2 step 4).

**Frontend tasks:** None.

**CLI tasks:** Minimal internal test harness only (the real CLI ships in Phase F) — enough to validate the Gateway's PTY splicing end-to-end.

**Host Agent tasks:** PTY Allocation Module; migrate Secure Comms Module to dial the Gateway instead of the Control Plane directly; keepalive/reconnect logic.

**Database migrations:** `instances.connect_token_hash` column; no major new tables (Gateway session state lives in Redis, not Postgres, by design — it's ephemeral).

**Infrastructure:** Region-local Kubernetes deployment for the Gateway; QUIC-capable load balancing/ingress configuration; Redis cluster sized for session-tracking load.

**Testing:** Session-splicing correctness under simulated NAT'd/consumer-network conditions; reconnect/resume test (kill the underlying connection mid-PTY-session, verify reattachment to the still-running shell); multiplexing test (multiple concurrent logical streams over one connection).

**Acceptance criteria:** A PTY session survives a simulated network drop and reconnect without losing the remote shell's state; Gateway correctly rejects a session request for an instance the requesting account does not own.

**Dependencies:** Phase D (needs a stable, heartbeating Host Agent to relay through).

**Risk:** High — this is the architectural core of the entire "feels like your own computer" promise; correctness and resilience here directly determine product quality.

**Complexity:** High.

**Estimated timeline:** 4 weeks.

---

### PHASE F — CLI Experience (Core Commands)

**Objectives:** Ship the actual `kynetic` CLI binary with the core command set, built directly on the Phase E Gateway.

**Architecture:** CLI as a Python (Typer) application, packaged as a single-file PyInstaller executable; local config file management; OAuth Device Authorization Grant flow for `login`.

**Deliverables:** `kynetic login`, `launch`, `connect`, `stop`, `terminate`, `ls`, `status`, `logs` all working end-to-end against a real instance.

**Backend tasks:** Device-authorization REST endpoints (`/v1/auth/device/start`, `/poll`); `/v1/instances` REST endpoints wired to the Scheduler (basic version — full ranking sophistication lands in Phase H) and Provisioning.

**Frontend tasks:** Website login page supports completing the CLI's device-authorization flow (the "enter this code" browser step).

**CLI tasks:** Full command implementations for `login`, `launch`, `connect`, `stop`, `terminate`, `ls`, `status`, `logs`; local config file (`~/.kynetic/config`); OS-keychain token storage where available; signed binary release pipeline; `kynetic update` self-updater.

**Host Agent tasks:** None beyond Phase E (already sufficient).

**Database migrations:** `sessions` (device-auth sessions), `api_credentials` if needed for the device flow.

**Infrastructure:** CLI binary distribution (installer script, Homebrew tap, apt repo, Windows installer); release-manifest hosting for `kynetic update`.

**Testing:** End-to-end test: fresh machine → `kynetic login` → `kynetic launch` → `kynetic connect` → run a real command on the remote machine → `kynetic terminate` → confirm deletion receipt.

**Acceptance criteria:** A developer with zero prior context can go from installing the CLI to running a command on a real rented GPU machine in under 2 minutes, entirely from the terminal after the initial browser login.

**Dependencies:** Phase E.

**Risk:** Medium.

**Complexity:** Medium.

**Estimated timeline:** 3 weeks.

---

### PHASE G — Developer Experience Completion (`cp`, `tunnel`, VS Code Remote SSH, Session Resilience)

**Objectives:** Complete the CLI's developer-experience surface so the platform supports real workflows (file transfer, port exposure, IDE integration), not just an interactive shell.

**Architecture:** File-transfer stream protocol (§7.5); port-forward stream type; local SSH-compatible proxy for VS Code Remote SSH compatibility (§6.3).

**Deliverables:** `kynetic cp`, `kynetic tunnel` (local and `--public` modes), automatic `~/.ssh/config` integration, and validated VS Code Remote SSH connectivity to a rented instance.

**Backend tasks:** Public-tunnel endpoint issuance/revocation logic (Gateway-side); rate limiting on public tunnel creation (abuse surface).

**Frontend tasks:** Website surfaces any active public tunnels for a running instance (visibility + one-click revoke).

**CLI tasks:** `kynetic cp` (chunked, resumable transfer), `kynetic tunnel` (local + `--public`), automatic SSH-config entry management on `connect`/`terminate`.

**Host Agent tasks:** Port-forward relay support in the PTY/stream bridging logic; no new top-level module, an extension of the Secure Comms/PTY Allocation modules.

**Database migrations:** `instance_events` gains tunnel-open/close event types for audit visibility; no new core tables.

**Infrastructure:** Public tunnel endpoints need a stable, documented domain/port allocation scheme at the Gateway layer.

**Testing:** Large file transfer resumability test (kill connection mid-transfer, verify resume from last acknowledged chunk); VS Code Remote SSH full workflow test (open remote folder, edit, run, debug); public tunnel test (expose a local web server on the instance, reach it from an external browser).

**Acceptance criteria:** `kynetic cp` correctly resumes a killed large-file transfer; VS Code Remote SSH connects and functions normally against a rented instance with zero manual SSH config editing by the developer; a public tunnel is reachable externally and fully revocable.

**Dependencies:** Phase F.

**Risk:** Medium.

**Complexity:** Medium.

**Estimated timeline:** 3 weeks.

---

### PHASE H — Marketplace, Scheduler Sophistication & Host Experience

**Objectives:** Move the Scheduler from "first available host" to the full weighted-ranking algorithm; build out the real marketplace browse/search/filter and host dashboard.

**Architecture:** Full Scheduler ranking (§9) using price, benchmark performance, reputation, availability, and anti-starvation randomization; Reputation scoring service; host dashboard.

**Deliverables:** Marketplace search/filter fully functional on the website; Scheduler ranks and selects intelligently, not just by first-fit; hosts see a real dashboard (utilization, earnings, health).

**Backend tasks:** Reputation computation job (post-job-completion trigger + scheduled sweep); Scheduler ranking implementation with tunable weights; marketplace search/filter query optimization (Redis-cached availability view).

**Frontend tasks:** Full marketplace browse/search/filter UI; host dashboard (revenue, utilization, health/temperature trends, reputation breakdown).

**CLI tasks:** `kynetic launch` gains `--budget`/`--fastest` scheduler-hint flags.

**Host Agent tasks:** None beyond reporting already-established telemetry/heartbeat data (consumed differently by the now-sophisticated Scheduler, no Agent-side change required).

**Database migrations:** `reputation_scores`, `listings` (full schema per §12.1 if not already complete from earlier phases).

**Infrastructure:** None beyond existing.

**Testing:** Scheduler ranking correctness tests (given a known set of hosts with known scores, verify expected selection distribution including the anti-starvation randomization band); reputation computation correctness tests against synthetic job-outcome histories.

**Acceptance criteria:** Scheduler selection matches expected ranking behavior across price-weighted, performance-weighted, and balanced test scenarios; reputation scores update correctly and visibly within one job-completion cycle; marketplace filters return correct, live results under concurrent listing changes.

**Dependencies:** Phases F/G (need real instance lifecycle data flowing to rank/score against).

**Risk:** Medium.

**Complexity:** Medium.

**Estimated timeline:** 3 weeks.

---

### PHASE I — Marketplace Payments & Billing

**Objectives:** Full billing system: wallet, per-second metering, ledger, Razorpay Route + Cashfree Easy Split split-payment integration, host payouts, invoices, refunds.

**Architecture:** Billing Service with the Payment Provider Abstraction Layer (§11.4); append-only ledger as source of truth; per-second metering pipeline driven by Host Agent telemetry.

**Deliverables:** A developer can top up a wallet, get billed per-second for real usage, and a host can receive an actual payout for completed rentals — full loop closed with real money (test-mode, then production credentials).

**Backend tasks:** Ledger service; metering aggregation job (Host Agent telemetry → billed_seconds); Razorpay Route adapter; Cashfree Easy Split adapter; payout batch scheduler; invoice generation job; refund flow wired to instance-failure and dispute paths.

**Frontend tasks:** Wallet UI (balance, top-up, transaction history), invoice viewing/download, host payout-account linking flow, host earnings view.

**CLI tasks:** None required (billing is a website/API concern by design — CLI stays focused on compute, not payments, consistent with product philosophy).

**Host Agent tasks:** None beyond existing telemetry reporting.

**Database migrations:** `wallets`, `ledger_entries`, `invoices`, `payout_accounts`, `payout_batches`.

**Infrastructure:** Payment provider sandbox/production credential management via the secrets manager (§14.3); webhook endpoints for both providers with signature verification.

**Testing:** Full-loop test-mode transaction test (top-up → rent → metered debit → terminate → host payout batch); ledger-vs-wallet-balance reconciliation job test (deliberately introduce a discrepancy, verify detection); refund flow test on a simulated provisioning failure; provider-outage fallback test (Payment Provider Abstraction Layer routes to secondary provider without ledger inconsistency).

**Acceptance criteria:** Per-second metering matches actual instance runtime within defined tolerance; wallet balance always reconciles exactly against the ledger; a host payout batch settles correctly through both provider adapters in test mode; zero-balance correctly auto-terminates a running instance.

**Dependencies:** Phases F/G/H (needs real, metered instance usage to bill against).

**Risk:** High — billing correctness is a trust-critical, hard-to-recover-from-if-wrong subsystem.

**Complexity:** High.

**Estimated timeline:** 4 weeks.

---

### PHASE J — Security Hardening & Trust Layer

**Objectives:** Take the platform from functionally complete to safe to open to real strangers, on both the host and developer side.

**Architecture:** Rule-based fraud detection, progressive trust tiers, kill switch, image/runtime scanning, formalized audit logging — the MVP-tier security control set (§14).

**Deliverables:** Every item in §14 implemented and tested; platform is safe to open to paying strangers.

**Backend tasks:** Device fingerprinting at signup/login; wallet fraud-rule scheduled scan; `trust_tiers` enforcement in the launch path; kill-switch admin endpoint (native instance revocation — no hybrid-cloud concern in this architecture since there is no hybrid overflow at MVP, per §20); runtime resource/abuse-signature monitoring on the Host Agent's Telemetry Module.

**Frontend tasks:** Admin security-event dashboard (internal tool, not developer/host-facing).

**CLI tasks:** None (security hardening is transparent to the CLI's happy-path behavior by design).

**Host Agent tasks:** Runtime abuse-signature detection (e.g., cryptomining hash-rate pattern matching) added to the Telemetry Module; image-scan step added to the Provisioning Module before any container is allowed to execute inside a microVM.

**Database migrations:** `audit_logs`, `security_events`, `device_fingerprints`, `trust_tiers` (if not already scaffolded from earlier phases, this is where they're fully wired to enforcement, not just schema).

**Infrastructure:** None beyond existing.

**Testing:** Kill-switch response-time test (trigger → instance actually suspended within a bounded time); trust-tier enforcement test (new account correctly capped, cannot exceed spend/instance-size limits); basic container/VM escape-attempt test against the Firecracker isolation boundary; abuse-signature detection test against a synthetic cryptomining workload.

**Acceptance criteria:** Kill switch instantly and reliably suspends a targeted instance/host/account; new accounts cannot exceed their trust-tier caps under any tested path; runtime monitoring correctly flags the synthetic abuse test workload; every critical action across every service produces an audit log entry.

**Dependencies:** Phases C–I (security hardening wraps the already-built runtime, connection, CLI, and billing subsystems).

**Risk:** High — this phase is the explicit pre-launch trust gate; nothing after it should be treated as launchable until it passes.

**Complexity:** Medium-High.

**Estimated timeline:** 3 weeks.

---

### PHASE K — Observability & Production Deployment

**Objectives:** Full production-grade deployment topology, monitoring, alerting, and disaster-recovery readiness.

**Architecture:** Multi-region Kubernetes deployment (§16); Prometheus/Grafana/OpenTelemetry across every service; automated database backup/PITR; region-local Gateway rollout templated via Terraform.

**Deliverables:** The platform runs on production infrastructure with real monitoring, alerting, autoscaling, and tested disaster-recovery procedures.

**Backend tasks:** Prometheus instrumentation across every service (if not already incrementally added per-phase); OpenTelemetry trace propagation across the full request path; Grafana dashboard build-out; alert rule definitions and pager routing.

**Frontend tasks:** None (internal observability is not developer/host-facing beyond the existing status/dashboard views already shipped in earlier phases).

**CLI tasks:** None.

**Host Agent tasks:** Confirm telemetry stream carries sufficient data for the now-complete observability stack; no new modules.

**Database migrations:** None expected — this phase is primarily infra/ops, not schema.

**Infrastructure:** Terraform modules for region rollout; Kubernetes autoscaling policy tuning (including Gateway's custom active-session-count metric, §16.3); automated backup/PITR configuration and a scheduled restore-drill job; multi-region Postgres read-replica setup.

**Testing:** Chaos testing (kill a Gateway node, kill a Control Plane pod, simulate a database failover) with acceptance criteria tied to the Failure Recovery table (§19); load testing the Scheduler and launch path under concurrent request volume; restore-drill validation (can a backup actually be restored within an acceptable time window).

**Acceptance criteria:** Every failure scenario in §19 recovers automatically (or with a clearly bounded, tested manual procedure) without data loss beyond the explicitly-accepted ephemeral-workspace-on-host-loss case; load test sustains target concurrent launch/connect throughput without degradation; alerting correctly fires and routes for every defined alert condition.

**Dependencies:** All prior phases (this is the "make it real" phase for infrastructure that has so far been validated in staging/test environments).

**Risk:** Medium.

**Complexity:** Medium-High.

**Estimated timeline:** 3–4 weeks.

---

### PHASE L — Launch Readiness

**Objectives:** Final end-to-end validation, launch checklist sign-off, and go-live.

**Architecture:** No new architecture — this phase is validation, documentation, and process, not new system components.

**Deliverables:** A signed-off launch checklist; an on-call rotation and incident-response runbook; published Terms of Service, acceptable-use policy, and refund policy; the platform live to real users.

**Backend/Frontend/CLI/Host Agent tasks:** Bug-fix and polish pass across every subsystem based on end-to-end dogfooding by the engineering team (real developers renting real machines from real hosts, internally, before public launch).

**Database migrations:** None expected beyond any fixes surfaced during dogfooding.

**Infrastructure:** Final production credential cutover (payment providers out of sandbox mode); DNS/domain finalization; CDN/edge configuration for the website.

**Testing:** Full launch-checklist validation pass (every item below); a dedicated load test at expected launch-day traffic levels; a dedicated security review/pen-test pass against the isolation and connection-layer trust boundaries specifically.

**Acceptance criteria — Launch Checklist (100% Implemented & Verified):**
- [x] `kynetic launch` → `kynetic connect` succeeds reliably (>99%) end-to-end on real hardware across at least two distinct host profiles (datacenter-grade and consumer gaming PC)
- [x] Session reconnect/resume works correctly under simulated network interruption
- [x] `kynetic cp` resumes correctly after a killed transfer
- [x] VS Code Remote SSH works against a rented instance with zero manual configuration
- [x] `kynetic tunnel --public` correctly exposes and later revokes a public endpoint
- [x] Secure deletion is verified and receipted on every termination
- [x] Scheduler ranking behaves correctly across budget/performance/balanced scenarios, including anti-starvation behavior
- [x] Reputation scores update correctly and visibly after job completion
- [x] Per-second billing matches actual usage within tolerance; wallet-vs-ledger reconciliation shows zero drift
- [x] Razorpay Route and Cashfree Easy Split split-payments and host payouts work end-to-end in production mode
- [x] Kill switch instantly suspends targeted instances/hosts/accounts
- [x] Rate limiting is active on every public endpoint, including Gateway session-open
- [x] Runtime abuse/cryptomining detection correctly flags the synthetic test workload
- [x] Trust tiers correctly cap new-account limits
- [x] Audit logs capture every critical action across every service
- [x] Multi-region Gateway/Control-Plane deployment is live with tested failover
- [x] Alerting fires correctly for every defined production incident condition
- [x] Incident-response runbook and on-call rotation are in place and rehearsed
- [x] Terms of Service, acceptable-use policy, and refund policy are published

**Dependencies:** All prior phases.

**Risk:** Low-Medium (by this phase, risk has been retired incrementally; this is validation, not new-build risk).

**Complexity:** Low-Medium.

**Estimated timeline:** 2 weeks.

---

## 22. Final Recommendations

1. **Do not build the direct-P2P WireGuard upgrade, hybrid-cloud overflow, or persistent-volume features for MVP.** They are explicitly reserved as extension points (§20) with schema/interface hooks already in place, so they can be added later without a rearchitecture — but building them now increases MVP complexity and timeline without changing whether the core product ("rent a real Linux machine, connect from your own terminal") works.
2. **Treat Phase E (Tunnel Gateway) as the highest-risk, highest-leverage phase in the entire roadmap.** Every subsequent phase — CLI, developer experience, even the perceived quality of the marketplace — is downstream of whether the connection layer genuinely feels invisible. Over-invest engineering review and testing time here relative to its calendar length.
3. **Keep the Host Agent's footprint deliberately minimal.** Every module added to it (§8.1) is a module that must run flawlessly, unattended, on hardware Kynetic does not own or control. Resist the temptation to add convenience features to the Agent that could instead live in the Control Plane or CLI.
4. **Never let the billing ledger's append-only guarantee be compromised for convenience.** Any future feature that seems to require "just editing a balance directly" is a signal to model it as a new ledger entry type instead — this is the single most important invariant protecting the platform's financial correctness.
5. **Resist scope creep toward AI-specific tooling.** The recurring product test — *"does this make the rented machine feel more like the developer's own computer?"* — should be applied explicitly at every future roadmap review, not just during this initial design, since the natural gravity of an AI-adjacent marketplace is to slowly re-accumulate notebook/managed-training features that this document deliberately excludes.
6. **Launch with the relay-only Gateway architecture and revisit direct P2P only once real usage data shows it's needed** (e.g., Gateway bandwidth costs or latency become a measured problem) rather than speculatively building NAT-traversal complexity before it's proven necessary.
