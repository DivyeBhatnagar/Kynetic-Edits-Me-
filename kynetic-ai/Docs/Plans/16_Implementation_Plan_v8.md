# Kynetic AI — Implementation Plan v8

### Extension Scope: GPU Benchmark & Health Score · Host Reputation · Verified Hosts · GPU Benchmark Database · Smart Search · One Command Launch

> **Continuity note:** This document extends the existing platform (Control Plane, Tunnel Gateway, Host Agent, Scheduler, `kynetic` CLI, PostgreSQL/Redis/Celery, Python/FastAPI stack) as specified in the prior Technical Design Document and Engineering Implementation Plan v6. Nothing below redesigns billing, the Scheduler's core ranking algorithm, the connection/tunnel architecture, or the isolation model — every feature reuses existing services (`marketplace_service`/Scheduler, `reputation_pricing_service`, `provisioning_service`, Host Agent modules, Tunnel Gateway) and extends them additively.

---

## 1. GPU Benchmark & Health Score

### 1.1 Executive Summary
Extends the Host Agent's existing **Benchmark Module** (previously: LLM inference, image-gen, raw FLOPs) into a full hardware-characterization suite, and extends `reputation_pricing_service`'s existing scoring logic with two new first-class scores — **Performance Score** and **Health Score** — that feed the Scheduler's existing ranking function and the marketplace listing display. No new service is created; this is an expansion of `host_benchmarks`, `host_heartbeats`, and the existing Celery benchmark-scheduling jobs.

### 1.2 Architecture
The Benchmark Module gains sub-benchmarks, each a discrete, independently-runnable Celery-triggered task on the Host Agent side: GPU (tensor core FP16/FP32 throughput, memory bandwidth via a bandwidth-saturation microbenchmark, PCIe bandwidth via host-to-device transfer timing), CPU (single/multi-core throughput), RAM bandwidth, disk speed (sequential/random read-write on the ephemeral NVMe volume), and network bandwidth (throughput test against a fixed nearby Control-Plane-operated speed-test endpoint). Thermal, power-draw, and clock-stability data are sampled continuously by the existing Heartbeat Module rather than as a discrete benchmark, since they characterize behavior under sustained load, not a point-in-time score.

### 1.3 System Components
No new services. Extended: Host Agent Benchmark Module (new sub-tests), Host Agent Heartbeat Module (adds clock-stability sampling), `reputation_pricing_service` (new score computation), `marketplace_service` (surfaces scores on listings).

### 1.4 Database Design
Extends `host_benchmarks` with a `metrics` JSONB payload per run (`gpu_model, cuda_version, driver_version, tensor_fp16_tflops, tensor_fp32_tflops, mem_bandwidth_gbps, pcie_bandwidth_gbps, vram_gb, disk_seq_mbps, disk_rand_iops, cpu_score, ram_bandwidth_gbps, net_bandwidth_mbps`).

New table `host_benchmark_runs` supersedes ad-hoc storage for individual sub-test results (id, host_id, run_id, benchmark_type, value, unit, run_at) — kept separate from the composite `host_benchmarks` row so trend queries (§4) don't require JSONB unpacking.

New table `host_scores` (host_id, performance_score, health_score, reliability_score, composite_score, computed_at) — replaces the single `composite_score` field previously embedded directly in `reputation_scores`; `reputation_scores` (Host Reputation, §2) now references `host_scores.reliability_score` rather than recomputing it, avoiding duplicate logic.

### 1.5 API Design
```
POST /hosts/{id}/benchmarks/run          (admin/scheduled trigger — reuses existing endpoint)
GET  /hosts/{id}/benchmarks               (existing, extended response shape)
GET  /hosts/{id}/benchmarks/history       (new — time series for trend charts)
GET  /hosts/{id}/scores                   (new — performance/health/reliability breakdown)
```

### 1.6 Sequence Diagram (Scheduled Re-Benchmark)
```
Celery Beat        Provisioning Svc        Host Agent           reputation_pricing_service
    │                     │                     │                          │
    │──trigger (per host)─▶│                     │                          │
    │                     │──RunBenchmarkSuite──▶│                          │
    │                     │                     │─run GPU/CPU/RAM/disk/net─│
    │                     │◄──signed results─────│                          │
    │                     │──store host_benchmark_runs, host_benchmarks────▶│
    │                     │                     │                          │──recompute host_scores
```

### 1.7 State Machine
`scheduled → running → completed` / `failed (retry with backoff, max 3)` / `flagged (result outside expected envelope for this GPU model — see §1.11)`.

### 1.8 Data Flow
Host Agent runs suite locally → signs results with its mTLS identity key → reports over existing Gateway control stream → `reputation_pricing_service` Celery task recomputes `host_scores` → `marketplace_service` listing cache (Redis) invalidated so search/browse reflects updated scores immediately.

### 1.9 Backend Changes
`reputation_pricing_service`: new `performance_score` (normalized against GPU-model peer group — a 4090 is scored relative to other 4090s, not against an H100) and `health_score` (rolling thermal/power/clock-stability stability over trailing 7-day heartbeat window) computation jobs. `marketplace_service`: listing serializer includes score breakdown.

### 1.10 Frontend Changes
Host dashboard: benchmark trend chart (reuses existing dashboard from Phase 8 of the platform roadmap), score breakdown card. Marketplace listing card: performance/health badges.

### 1.11 CLI / Host Agent Changes
CLI: none required for this feature directly (surfaces via `kynetic launch`/search, §6). Host Agent: sub-benchmark implementations; a **result-envelope check** — each GPU model has an expected performance range (maintained server-side, §1.13) and a Host Agent result outside that envelope is flagged rather than silently accepted, pending re-run.

### 1.12 Scheduler Changes
None to the ranking algorithm itself — `performance_score` and `health_score` are new inputs the existing weighted-scoring function already has a slot for (the Scheduler's `perf_score` and `availability_score` terms are now backed by richer data, not restructured).

### 1.13 Admin Dashboard
Internal view: per-GPU-model expected-performance envelope management (min/max thresholds used for fraud/flag detection), flagged-benchmark review queue.

### 1.14 Testing Strategy
Repeatability tests (same host, same score within tolerance across consecutive runs); envelope-violation detection tests (inject a synthetic out-of-range result, confirm flagging); peer-group normalization correctness (two different 4090s should score close to each other; a 4090 and an H100 should not be compared on raw scale).

### 1.15 Security
Every benchmark result is signed by the Host Agent's existing mTLS identity — an unsigned or badly-signed result is rejected outright. Results are never accepted from any path other than the authenticated Gateway control stream.

### 1.16 Fraud Prevention & Manipulation Detection
1. **Peer-group envelope checks** (§1.11/1.13) — the primary defense; a spoofed/fake GPU claiming 4090-class VRAM but failing to hit 4090-class tensor throughput is flagged automatically.
2. **Consistency-over-time checks** — a host whose benchmark score suddenly jumps or degrades outside normal variance between scheduled runs is flagged for manual re-verification (ties into Host Reputation's automatic penalty path, §2.9).
3. **Cross-validation against declared hardware** — `host_hardware` (existing spec-cross-check table) must agree with the GPU model claimed by the benchmark result; mismatch blocks listing activation.
4. **No self-reported override** — a host can never manually edit a benchmark score; only a re-run of the actual suite can change it.

### 1.17 Failure Recovery
Failed benchmark run retries with backoff (max 3 attempts) before marking the host `flagged` for manual review rather than silently leaving stale scores; a host that goes offline mid-benchmark simply resumes on next heartbeat-triggered re-run.

### 1.18 Observability
Prometheus metrics: benchmark run success/failure rate, average duration per sub-test, flagged-result rate. Alert on flagged-rate spike (possible fleet-wide fraud pattern or a benchmark-suite regression).

### 1.19 Scaling Strategy
Benchmark runs are Celery-distributed and rate-limited per host (never more than one concurrent benchmark run per host, so a fleet-wide scheduled re-benchmark doesn't create a thundering herd against `reputation_pricing_service`); results are batched into `host_benchmark_runs` via bulk insert.

### 1.20 Implementation Phases
**Phase 1:** Sub-benchmark suite (GPU/CPU/RAM/disk/network) on Host Agent. **Phase 2:** `host_benchmark_runs`/`host_scores` schema + recomputation jobs. **Phase 3:** Peer-group envelope + fraud flagging. **Phase 4:** Dashboard/marketplace surfacing.

### 1.21 Acceptance Criteria
- [ ] All sub-benchmarks run automatically on schedule and on-demand
- [ ] Performance/health/reliability scores compute correctly and update within one Celery cycle of a new run
- [ ] Peer-group envelope checks correctly flag a synthetic spoofed result
- [ ] Score breakdown is visible on host dashboard and marketplace listings

### 1.22 Complexity
Medium-High (peer-group normalization and envelope calibration require real fleet data to tune).

### 1.23 Dependencies
Existing Host Agent Benchmark/Heartbeat Modules, `reputation_pricing_service`, `marketplace_service`.

### 1.24 Future Improvements
ML-based anomaly detection replacing static envelopes once sufficient fleet history exists; per-region performance-envelope calibration (thermal throttling varies by climate).

---

## 2. Host Reputation System

### 2.1 Executive Summary
Formalizes and extends the existing `reputation_scores` mechanism (previously: uptime, latency, network, job success, benchmark, response time) into a full trust/reputation system with explicit weighting, time-decay, dispute/refund/violation tracking, and automatic penalty/recovery — still owned by `reputation_pricing_service`, no new service.

### 2.2 Architecture
A single **composite reputation score**, recomputed on every completed/cancelled/failed job and on a nightly decay sweep, built from weighted sub-scores stored individually so each is independently auditable and independently decayable.

### 2.3 System Components
`reputation_pricing_service` (existing) — extended computation logic and new Celery decay job. No new services.

### 2.4 Database Design
Extends `reputation_scores` with new columns: `completed_jobs, cancelled_jobs, failed_jobs, avg_uptime_pct, connection_reliability_pct, provision_success_rate, avg_response_latency_ms, benchmark_stability_score (references host_scores.health_score), avg_user_rating, dispute_count, refund_count, policy_violation_count, host_age_days, machine_age_days, decay_factor, last_decayed_at`.

New table `reputation_events` (id, host_id, event_type[job_completed|job_cancelled|job_failed|dispute_opened|refund_issued|violation_flagged|manual_penalty|manual_restore], impact_delta, metadata JSONB, created_at) — the append-only event log the composite score is derived from, mirroring the ledger's append-only design principle already used for billing.

### 2.5 API Design
```
GET  /hosts/{id}/reputation                 (existing, extended response)
GET  /hosts/{id}/reputation/history         (new — event trail)
POST /admin/hosts/{id}/reputation/penalty   (admin manual action)
POST /admin/hosts/{id}/reputation/restore   (admin manual action)
```

### 2.6 Sequence Diagram (Job Completion → Reputation Update)
```
provisioning_service        reputation_pricing_service         Postgres
       │                            │                              │
       │──instance.terminated───────▶│                              │
       │  (job outcome: success/fail)│                              │
       │                            │──write reputation_events─────▶│
       │                            │──recompute weighted composite│
       │                            │──write reputation_scores─────▶│
       │                            │──invalidate marketplace cache│
```

### 2.7 State Machine (Host Trust State)
`new → building_trust → established → (flagged on abuse signal) → suspended → (manual review) → restored/permanently_banned`. This layers on top of, and is distinct from, the existing `trust_tier` spend/instance-cap mechanism — trust state gates listing visibility, `trust_tier` gates transaction limits.

### 2.8 Data Flow
Every `instance` lifecycle terminal state (`terminated`, `failed`) and every billing dispute/refund event (from the existing wallet ledger) emits a `reputation_events` row via a lightweight event hook, not a tight coupling — `wallet_billing_service` and `provisioning_service` publish events; `reputation_pricing_service` consumes them (Redis pub/sub, reusing the existing message infrastructure rather than introducing a new bus).

### 2.9 Weighting, Decay & Automatic Penalties
**Weighting (illustrative starting weights, tunable):** job success rate 25%, uptime 20%, connection reliability 15%, provision success rate 15%, benchmark stability 10%, user rating 10%, response latency 5% — minus a penalty term for disputes/refunds/violations.

**Decay:** a nightly Celery job applies exponential decay to the *influence* of old events (not the events themselves, which remain in the immutable `reputation_events` log) — a job completed 6 months ago contributes less to the current composite than one completed yesterday, so reputation reflects recent behavior, not permanent history. Decay half-life is configurable per event type (violations decay slower than routine completions).

**Automatic penalties:** a policy-violation or fraud-flag event (including a benchmark-fraud flag from §1.16) triggers an immediate composite-score penalty and, past a threshold, an automatic transition to `flagged` trust state (reduced marketplace visibility) without waiting for the nightly recompute.

**Automatic recovery:** sustained clean behavior (no new negative events) over a defined window allows the decay mechanism to naturally restore score — no separate "recovery job" is needed since decay already handles this by construction.

### 2.10 Backend Changes
`reputation_pricing_service`: event-consumption worker, weighted-composite computation, nightly decay job. `wallet_billing_service`/`provisioning_service`: emit `reputation_events` on relevant transitions (additive hook, no change to their own core logic).

### 2.11 Frontend Changes
Host dashboard: reputation breakdown, event history, trust-state banner. Marketplace listing: reputation badge (existing, now backed by richer data).

### 2.12 CLI / Host Agent Changes
None required — reputation is a marketplace/trust concern surfaced via search (§5) and the website, not a CLI-facing primitive.

### 2.13 Scheduler Changes
None — the Scheduler already consumes `reputation_scores.composite_score`; only the data backing it is richer.

### 2.14 Admin Dashboard
Reputation event review queue, manual penalty/restore actions (both logged as `reputation_events` with `event_type = manual_penalty|manual_restore`, preserving full audit trail), decay-weight configuration panel.

### 2.15 Testing Strategy
Weighted-composite computation correctness tests against known event histories; decay-curve tests (verify old events lose influence at the expected rate); automatic-penalty threshold tests; anti-gaming test (a host cannot inflate its score by rapidly self-cancelling low-risk jobs — cancelled jobs carry a small negative weight, not zero, to remove that incentive).

### 2.16 Security
`reputation_events` is append-only, mirroring the billing ledger's integrity model; only the automated pipeline and explicit admin actions (fully audited) can write to it — no direct score mutation path exists anywhere in the system.

### 2.17 Anti-Abuse Mechanisms
- Weighted job-outcome scoring prevents "volume gaming" (many trivial jobs) from outweighing genuine reliability signals, since success **rate**, not raw count, dominates the weighting.
- Cancelled jobs carry a small penalty to remove incentive for hosts to cherry-pick only easy/short jobs.
- Manual penalty/restore actions require admin authentication and are themselves logged, preventing insider abuse of the override path.
- Cross-linkage to benchmark fraud flags (§1.16) means gaming one subsystem (benchmarks) has consequences in another (reputation), raising the cost of coordinated manipulation.

### 2.18 Failure Recovery
If the event-consumption worker falls behind or crashes, `reputation_events` (durable, append-only) guarantees no data loss — the worker simply resumes consumption and recomputation from where it left off; nightly decay job re-runs are idempotent (deterministic given the event log + current timestamp).

### 2.19 Observability
Metrics: event-processing lag, decay-job duration, penalty/restore action rate (spike may indicate a policy or fraud-detection change worth reviewing). Alert on event-processing lag exceeding a threshold (marketplace scores going stale).

### 2.20 Scaling Strategy
Event-sourced design means the composite score is always a derived, cache-friendly value (recomputed incrementally on new events, not recomputed from the full event history each time) — same pattern already proven by the billing ledger's wallet-balance caching.

### 2.21 Implementation Phases
**Phase 1:** `reputation_events` schema + event emission hooks from existing services. **Phase 2:** Weighted-composite computation + decay job. **Phase 3:** Automatic penalty/recovery + trust-state machine. **Phase 4:** Admin dashboard + anti-abuse tuning.

### 2.22 Acceptance Criteria
- [ ] Composite score correctly reflects weighted inputs and recent-behavior decay
- [ ] Automatic penalty triggers correctly and immediately on a violation/fraud event
- [ ] Manual admin actions are fully audited and reversible
- [ ] Cancelled-job gaming strategy does not improve a host's score in testing

### 2.23 Complexity
Medium-High.

### 2.24 Dependencies
§1 (benchmark stability feeds reputation), existing wallet ledger (disputes/refunds), existing `instances` lifecycle events.

### 2.25 Future Improvements
User-submitted qualitative feedback beyond a numeric rating; ML-based anomaly detection on event patterns once fleet history is sufficient.

---

## 3. Verified Hosts

### 3.1 Executive Summary
Adds a formal, tiered verification program (Silver/Gold/Enterprise) on top of the existing host onboarding flow (phone verification already exists from the platform's Phase 1/5 trust-tier work) — extending `auth_service` and `marketplace_service`, not replacing them.

### 3.2 Architecture
A verification request moves through a state machine combining automatic checks (phone/email, already built; payment/bank account validity via the existing payment-provider abstraction) and manual review (identity document, business registration) gated by an admin queue.

### 3.3 System Components
`auth_service` (identity/document verification workflow), new lightweight `verification` module within it (not a new service — reuses `auth_service`'s existing account/trust-tier infrastructure), admin review tooling.

### 3.4 Database Design
New table `host_verifications` (id, host_id, level[silver|gold|enterprise], status[pending|in_review|approved|rejected|revoked], submitted_at, reviewed_by, reviewed_at, rejection_reason).

New table `verification_documents` (id, verification_id, document_type[gov_id|business_registration|bank_statement|utility_bill], storage_url, uploaded_at, status[pending|verified|rejected]) — files stored in the existing S3-compatible object storage, never in the primary database.

Extends `hosts` with `verification_level` (denormalized for fast marketplace filtering, kept in sync via the state machine transition, not independently editable).

### 3.5 API Design
```
POST /hosts/{id}/verification/apply          (level, documents[])
GET  /hosts/{id}/verification/status
POST /admin/verifications/{id}/approve
POST /admin/verifications/{id}/reject
POST /admin/verifications/{id}/revoke
GET  /admin/verifications?status=pending      (review queue)
```

### 3.6 Sequence Diagram (Verification Submission → Approval)
```
Host (website)     auth_service         Object Storage      Admin Reviewer
     │                   │                     │                   │
     │──submit docs──────▶│                     │                   │
     │                   │──upload─────────────▶│                   │
     │                   │──create host_verifications (pending)─────│
     │                   │──auto-checks (phone/email/payment)────────│
     │                   │──status: in_review─────────────────────▶│
     │                   │                     │◄──review decision──│
     │                   │◄──approve/reject────────────────────────│
     │◄──status updated───│                     │                   │
```

### 3.7 State Machine
`unverified → pending → in_review → approved (level assigned)` / `rejected (reason recorded, resubmission allowed)` / `approved → revoked (policy violation or reputation collapse — cross-linked to §2's trust-state machine)`.

### 3.8 Verification Levels
- **Silver:** phone + email verified (already exists), government ID verified. Minimum bar for any listing beyond the existing new-account `trust_tier` caps.
- **Gold:** Silver + bank/payout account verified (reuses existing Stripe Connect/Razorpay account-linking from the billing system) + sustained clean reputation history (§2) over a minimum window.
- **Enterprise:** Gold + business registration document + manual admin interview/approval — intended for datacenter/fleet operators, not individual hosts.

### 3.9 Data Flow
Documents uploaded directly to object storage via a pre-signed URL (never proxied through the API server); metadata/status tracked in Postgres; approval triggers a `hosts.verification_level` update and a marketplace-cache invalidation so search/filter (§5) reflects the new badge immediately.

### 3.10 Backend Changes
`auth_service`: verification submission/status endpoints, document pre-signed-upload issuance. `marketplace_service`: listing serializer includes `verification_level`; search/filter support (§5).

### 3.11 Frontend Changes
Host onboarding flow: verification application UI per level, document upload, status tracker. Marketplace: verification badge on listings.

### 3.12 CLI / Host Agent Changes
None — verification is an identity/trust concern handled on the website, consistent with the platform principle that the website owns auth/billing/marketplace administration while the CLI stays focused on compute.

### 3.13 Scheduler Changes
None directly — verification level is a new optional filter/ranking signal a developer can weight in `kynetic launch`/search (§5, §6), not a change to the Scheduler's core algorithm.

### 3.14 Admin Dashboard
Review queue (pending/in_review verifications), document viewer, approve/reject/revoke actions with mandatory reason capture, per-level approval-rate and average-review-time metrics.

### 3.15 Moderation Tools
Manual revoke (with cascading effect: revocation immediately downgrades `verification_level` and is logged as a `reputation_events` entry, since a revoked verification is itself a trust-relevant event); bulk re-review trigger for a document type found to have a systemic fraud pattern (e.g., a batch of forged IDs from one source).

### 3.16 Testing Strategy
State-machine transition tests (every valid/invalid transition); document pre-signed-URL expiry/security tests; auto-check correctness tests (payment/bank verification against the existing provider abstraction's sandbox mode); revocation cascade test (verify `reputation_events` entry and marketplace visibility update).

### 3.17 Security
Documents stored with restricted, time-limited access (pre-signed URLs, admin-only retrieval); PII in `verification_documents` encrypted at rest (extends the existing encryption-at-rest posture already applied to wallet/payment-linked tables); full audit trail via existing `audit_logs`.

### 3.18 Failure Recovery
A stuck `in_review` verification beyond an SLA window triggers an internal alert (not an automatic approval — verification failures fail closed, never open); document upload failures are retried client-side against a freshly-issued pre-signed URL.

### 3.19 Observability
Metrics: submissions per level, approval/rejection rate, average review latency, revocation rate. Alert on review-queue backlog exceeding SLA.

### 3.20 Scaling Strategy
Manual review is the inherent bottleneck by design (Enterprise level explicitly requires it) — the architecture scales the automatic-check portion (phone/email/payment) fully, and treats manual-review throughput as an operations staffing concern, not an engineering one.

### 3.21 Implementation Phases
**Phase 1:** `host_verifications`/`verification_documents` schema + Silver-level automatic-check flow. **Phase 2:** Document upload + manual review queue + admin dashboard. **Phase 3:** Gold/Enterprise levels + revocation cascade into reputation.

### 3.22 Acceptance Criteria
- [ ] A host can apply for and receive Silver verification via fully automatic checks
- [ ] Gold/Enterprise applications correctly route to manual review with document access
- [ ] Revocation immediately reflects in marketplace visibility and reputation history
- [ ] All PII documents are encrypted at rest and access-logged

### 3.23 Complexity
Medium.

### 3.24 Dependencies
Existing `auth_service` phone/email verification and `trust_tier` mechanism, existing payment-provider account-linking, §2 (reputation cross-link).

### 3.25 Future Improvements
Third-party KYC/AML provider integration to automate identity/business document checks currently requiring manual review; recurring re-verification cadence for Enterprise hosts.

---

## 4. GPU Benchmark Database

### 4.1 Executive Summary
Aggregates the per-host benchmark data already produced by §1 into a centralized, queryable, cacheable analytics layer supporting historical trends, regional/model comparisons, and price/performance rankings — an analytical extension of `host_benchmark_runs`, not a new source of truth.

### 4.2 Architecture
A read-optimized layer sitting on top of `host_benchmark_runs`/`host_benchmarks`: materialized views for common aggregations, refreshed on a schedule, backed by Redis caching for the hottest queries (GPU-model leaderboards, regional averages).

### 4.3 System Components
`reputation_pricing_service` (owns the benchmark data already) gains an aggregation module; `marketplace_service` exposes the query API. No new service.

### 4.4 Database Design
Materialized view `mv_gpu_model_stats` (gpu_model, region, avg_tensor_fp16_tflops, avg_tensor_fp32_tflops, avg_mem_bandwidth_gbps, sample_count, last_refreshed) — refreshed nightly via Celery-triggered `REFRESH MATERIALIZED VIEW CONCURRENTLY`.

Materialized view `mv_price_performance` (gpu_model, region, avg_price_per_hour, avg_performance_score, price_performance_ratio) joining `listings` with `host_scores`.

Both views are additive read paths; no change to the underlying `host_benchmark_runs`/`host_benchmarks` write path from §1.

### 4.5 API Design
```
GET /benchmarks/gpu-models                        (list all tracked GPU models with summary stats)
GET /benchmarks/gpu-models/{model}                 (detail: historical trend, regional breakdown)
GET /benchmarks/gpu-models/{model}/compare?with=X  (side-by-side comparison)
GET /benchmarks/price-performance                  (rankings, filterable by region)
```

### 4.6 Sequence Diagram (Nightly Aggregation)
```
Celery Beat          reputation_pricing_service          Postgres              Redis
     │                        │                              │                   │
     │──trigger (nightly)─────▶│                              │                   │
     │                        │──REFRESH MATERIALIZED VIEWS──▶│                   │
     │                        │◄──refresh complete─────────────│                   │
     │                        │──warm cache (top GPU models, price/perf rankings)──▶│
```

### 4.7 State Machine
Not applicable — this is a read/aggregation layer, not a lifecycle-bearing entity.

### 4.8 Data Flow
`host_benchmark_runs` (write path, unchanged from §1) → nightly materialized-view refresh → Redis cache warm → API reads serve from cache first, materialized view on cache miss, raw table only for ad-hoc admin analytics queries.

### 4.9 Backend Changes
New aggregation Celery job; new read-only API endpoints in `marketplace_service`.

### 4.10 Frontend Changes
Public "GPU comparison" page (marketplace-adjacent, informational — supports the developer's pre-launch decision-making); host dashboard "how does my machine compare" widget.

### 4.11 CLI / Host Agent Changes
None directly, though `kynetic launch`'s search/filter (§5, §6) is a consumer of the same underlying scores.

### 4.12 Scheduler Changes
None — this is an analytics/discovery layer, not a scheduling input beyond what §1's `host_scores` already provides.

### 4.13 Admin Dashboard
Raw aggregation-job health view (last refresh time, row counts, refresh duration) — operationally focused, not developer-facing.

### 4.14 Testing Strategy
Materialized-view refresh correctness (verify aggregation math against a known synthetic dataset); cache-invalidation tests (stale cache never served past the configured TTL); comparison-endpoint tests (two known GPU models compare correctly).

### 4.15 Security
Read-only, no PII, no host-identifying data beyond aggregate/anonymized GPU-model-level stats — individual host benchmark results remain gated behind the existing host/admin authorization from §1, this layer only ever exposes aggregates.

### 4.16 Failure Recovery
A failed materialized-view refresh leaves the previous (still valid, just stale) view in place — `CONCURRENTLY` refresh guarantees readers are never blocked or served a partial result; failure triggers a retry and an alert, not an outage.

### 4.17 Observability
Metrics: refresh job duration/success rate, cache hit rate on comparison/ranking endpoints, query latency on the comparison API.

### 4.18 Scaling Strategy
Materialized views + Redis caching keep this entirely off the hot write path (billing, provisioning, live scheduling) — read load here can be scaled independently and does not risk contending with transactional workloads. Materialized-view refresh cost scales with GPU-model-count × region-count, not with raw benchmark-row-count, keeping refresh time bounded as the fleet grows.

### 4.19 Implementation Phases
**Phase 1:** Materialized views + nightly refresh job. **Phase 2:** Comparison/ranking API + Redis caching. **Phase 3:** Frontend comparison page + host "how do I compare" widget.

### 4.20 Acceptance Criteria
- [ ] GPU model comparison and price/performance ranking endpoints return correct, current data
- [ ] Nightly refresh completes without blocking live reads
- [ ] Cache correctly serves hot queries with measurable latency improvement over raw materialized-view queries

### 4.21 Complexity
Low-Medium.

### 4.22 Dependencies
§1 (data source), existing `listings`/pricing data.

### 4.23 Future Improvements
Explicit Elasticsearch/analytical-store migration path once aggregate query volume or dimensionality (e.g., arbitrary multi-attribute slicing) outgrows materialized-view refresh economics — the API contract in §4.5 is deliberately storage-agnostic so this migration would not require a client-facing breaking change.

---

## 5. Smart Search

### 5.1 Executive Summary
Extends the existing marketplace browse/filter (`marketplace_service`, previously: resource type, price, GPU model, region, reputation) into a full multi-attribute search and ranking engine spanning all the new signals from §1–§4, still backed by PostgreSQL for MVP with an explicit, non-disruptive path to Elasticsearch.

### 5.2 Architecture
A **filtering layer** (hard constraints — must match) composed with a **ranking layer** (soft scoring — best match first), both operating over a Redis-cached, denormalized "searchable listing" view that's kept in sync with `listings`, `host_scores`, `reputation_scores`, and `host_verifications` via the same cache-invalidation hooks already established in §1–§4 (any score/verification change already invalidates the relevant listing cache entries).

### 5.3 System Components
`marketplace_service` (existing) — extended query layer. No new service for MVP; Elasticsearch is explicitly deferred (§5.13).

### 5.4 Database Design
New denormalized `searchable_listings` table (materialized, refreshed incrementally on relevant upstream change rather than full nightly rebuild — a targeted upsert triggered by the same cache-invalidation events from §1/§2/§3): listing_id, gpu_model, cuda_version, vram_gb, tensor_fp16_tflops, performance_score, health_score, reputation_composite_score, verification_level, price_per_hour, region, country, cpu_cores, ram_gb, storage_gb, storage_type, network_bandwidth_mbps, os, availability_status, created_at.

Composite indexes: `(availability_status, region, price_per_hour)`, `(gpu_model, performance_score DESC)`, `(verification_level, reputation_composite_score DESC)` — covering the most common filter+sort combinations.

### 5.5 API Design
```
GET /search/listings?gpu_model=&cuda_version=&min_vram=&min_tensor_perf=
                     &min_health_score=&min_reputation=&verification_level=
                     &max_price=&region=&country=&max_latency_ms=
                     &min_cpu_cores=&min_ram_gb=&storage_type=&os=
                     &sort=price|performance|value|reputation|fastest|nearest|newest
                     &cursor=&limit=
```
Single endpoint, cursor-paginated (consistent with the existing platform-wide pagination convention), all filters optional and composable.

### 5.6 Sequence Diagram (Search Request)
```
kynetic CLI / Website        marketplace_service           Redis            Postgres
        │                          │                          │                 │
        │──GET /search/listings────▶│                          │                 │
        │                          │──check cached result for filter+sort key───▶│
        │                          │◄──cache hit───────────────│                 │
        │◄──ranked, paginated results│                          │                 │
        │                          │  (on cache miss)          │                 │
        │                          │──query searchable_listings─────────────────▶│
        │                          │──cache result (short TTL)──▶│                 │
```

### 5.7 State Machine
Not applicable — search is stateless per-request; the underlying `searchable_listings` row is kept fresh via event-driven upsert, not a lifecycle of its own.

### 5.8 Data Flow
Any write to `listings`, `host_scores` (§1), `reputation_scores` (§2), or `host_verifications` (§3) publishes an invalidation event (Redis pub/sub, reusing the bus already introduced in §2.8) → a lightweight consumer upserts the corresponding `searchable_listings` row → search queries always read from this near-real-time denormalized view rather than joining five tables on every request.

### 5.9 Ranking Engine
For `sort=value` ("best value"), a composite ranking score combines normalized price (inverse-weighted) and `performance_score`; `sort=fastest` ranks purely by `performance_score`; `sort=nearest` uses declared region/country with a latency-estimate tiebreaker (consistent with the existing Scheduler's MVP-tier "declared region, refine post-connect" approach — full real-time latency probing is not built for search, matching the platform's stated preference for simplicity over premature sophistication); `sort=newest` by `listings.created_at`; `sort=highest_reputation` by `reputation_composite_score`. All ranking computation happens in the SQL query (`ORDER BY` on precomputed, indexed columns) — no application-layer re-ranking pass, keeping latency predictable.

### 5.10 Backend Changes
`marketplace_service`: new `/search/listings` endpoint, `searchable_listings` upsert consumer, Redis caching layer for hot filter/sort combinations (short TTL, since availability changes frequently).

### 5.11 Frontend Changes
Website marketplace page: full filter UI (faceted, all attributes from §5.5), sort dropdown.

### 5.12 CLI / Host Agent Changes
`kynetic launch` (§6) is the primary CLI consumer of this exact API — no separate CLI-specific search logic, guaranteeing website and CLI search behave identically.

### 5.13 Future Elasticsearch Compatibility
The `/search/listings` API contract is deliberately storage-agnostic (flat filter/sort parameters, not SQL-shaped) — a future migration to Elasticsearch would swap `marketplace_service`'s internal query implementation (Postgres query against `searchable_listings` → Elasticsearch query against a synced index) without any client-facing (CLI or website) change. This migration is explicitly **not** built now — PostgreSQL with proper indexing and the denormalized `searchable_listings` table is judged sufficient for MVP search volume, consistent with the platform's "smallest architecture that can realistically launch" principle.

### 5.14 Testing Strategy
Filter-combination correctness tests (each filter independently and in combination); sort-order correctness tests per `sort` value; cache-invalidation freshness tests (a score/verification change must be reflected in search results within a bounded time); pagination correctness under concurrent listing changes (cursor-based, per existing platform convention, avoids the offset-pagination drift problem).

### 5.15 Security
Read-only endpoint, no auth required for browsing (consistent with the public marketplace), rate-limited at the API Gateway per the platform's existing rate-limiting middleware (no new mechanism).

### 5.16 Failure Recovery
Cache miss/Redis unavailability falls back transparently to direct Postgres query (degraded latency, not degraded correctness); a stalled `searchable_listings` upsert consumer is detected via lag metrics (§5.18) and does not corrupt data — worst case is temporarily stale search results, never incorrect ones, since the upsert is idempotent per listing.

### 5.17 Observability
Metrics: search query latency (p50/p95/p99), cache hit rate, `searchable_listings` upsert lag, filter-combination popularity (informs future index tuning).

### 5.18 Scaling Strategy
Denormalized `searchable_listings` + composite indexes keep query cost bounded regardless of how many upstream tables a full listing "view" logically spans; Redis caching absorbs repeat-query load (common filter combinations like "cheapest available GPU in region X" are hit far more than long-tail combinations). If/when Postgres index-based search stops scaling, §5.13's Elasticsearch path is the documented next step — not built preemptively.

### 5.19 Implementation Phases
**Phase 1:** `searchable_listings` schema + event-driven upsert consumer. **Phase 2:** `/search/listings` endpoint with full filter/sort support. **Phase 3:** Redis caching layer + website filter UI. **Phase 4:** `kynetic launch` integration (§6).

### 5.20 Acceptance Criteria
- [ ] All specified filters and sort options return correct results
- [ ] Search reflects a benchmark/reputation/verification change within a bounded, tested freshness window
- [ ] p95 search latency meets a defined target under simulated concurrent load
- [ ] Website and CLI search produce identical results for identical query parameters

### 5.21 Complexity
Medium.

### 5.22 Dependencies
§1–§3 (data sources), existing `listings`/marketplace infrastructure.

### 5.23 Future Improvements
Elasticsearch migration (§5.13) if scale demands it; personalized ranking based on a developer's past rental history; saved-search/alert notifications.

---

## 6. One Command Launch

### 6.1 Executive Summary
Extends the `kynetic` CLI with `kynetic launch` — an interactive, fully terminal-based flow from machine discovery through provisioning to automatic `kynetic connect` — built entirely on existing primitives (§5's search API, the existing Scheduler, the existing `POST /v1/instances` provisioning endpoint, the existing Gateway connection layer). No new backend service; this is a CLI-orchestration feature.

### 6.2 Architecture
The CLI drives a client-side wizard state machine that calls existing/extended APIs in sequence: search (§5) → developer selection → price confirmation → launch (existing `POST /v1/instances`) → poll provisioning status → auto-invoke the existing `connect` code path once `instance.status = running`.

### 6.3 System Components
`kynetic` CLI (extended), `marketplace_service` `/search/listings` (§5, reused as-is), `provisioning_service` `POST /v1/instances` (existing, reused as-is), Tunnel Gateway (existing, reused as-is for the automatic connect step). No new backend components.

### 6.4 Database Design
No new tables — `kynetic launch` produces the same `instances` row as any other launch path (website or direct API call); it is purely a new client-side entry point onto existing server-side state.

### 6.5 API Design
No new endpoints beyond §5's `/search/listings` and the existing `POST /v1/instances` / `GET /v1/instances/{id}`. `kynetic launch` is additive CLI orchestration only.

### 6.6 CLI UX Flow
```
$ kynetic launch

? What GPU do you need?           [search-as-you-type against /search/listings]
  > RTX 4090 (24GB)     $0.42/hr   perf: 94   rep: 4.8★   verified: Gold
    RTX 3090 (24GB)     $0.29/hr   perf: 78   rep: 4.6★   verified: Silver
    A100 (80GB)         $1.85/hr   perf: 99   rep: 4.9★   verified: Enterprise

? Region:                          [defaults to nearest based on account locale, editable]
  > us-east   (12 available)
    eu-west   (7 available)
    ap-south  (4 available)

? Duration:  [1h / 4h / 24h / custom] — informs the initial wallet hold, not a hard cutoff;
             developer can stop/terminate any time exactly as with any other launch path

? Confirm:  RTX 4090 · us-east · $0.42/hr · est. $1.68 for 4h    [Y/n]

Launching...        ⠋ provisioning (12s)
Connecting...        ✓ instance running
                     ✓ auto-connecting

$ (dropped directly into the remote shell — identical to a manual `kynetic connect`)
```

Every prompt supports non-interactive flags for scripting (`kynetic launch --gpu rtx-4090 --region us-east --duration 4h --yes`), so `kynetic launch` is both a guided wizard and a scriptable one-liner — consistent with the CLI-first product philosophy.

### 6.7 Sequence Diagram
```
Developer    kynetic CLI       marketplace_service      provisioning_service      Scheduler        Tunnel Gateway
    │             │                     │                        │                    │                 │
    │─launch──────▶│                     │                        │                    │                 │
    │             │──GET /search/listings──────────────────────────────────────────────│                 │
    │             │◄──ranked results─────│                        │                    │                 │
    │◄─prompt (select)─│                 │                        │                    │                 │
    │─selection───▶│                     │                        │                    │                 │
    │             │──POST /v1/instances (Idempotency-Key)─────────▶│                    │                 │
    │             │                     │                        │──rank/assign host──▶│                 │
    │             │                     │                        │◄──host selected──────│                 │
    │             │◄─instance_id, status=pending────────────────────│                    │                 │
    │             │──poll GET /v1/instances/{id}───────────────────▶│  (until running)   │                 │
    │             │◄─status=running──────────────────────────────────│                    │                 │
    │             │──dial Gateway, request PTY session (existing kynetic connect path)────────────────────▶│
    │◄════════════ spliced PTY stream, dropped into remote shell ═══════════════════════════════════════════│
```

### 6.8 State Machine (CLI-Side Wizard, Distinct From Server-Side `instances` Lifecycle)
`searching → selecting → confirming → launching → polling_provisioning → connecting → connected` / `failed_at_any_step (clear error, no partial charge — an unconfirmed launch never reaches the billing hold step)`.

### 6.9 Data Flow
Entirely a client-orchestrated sequence over existing server APIs (§6.5) — no new server-side data flow beyond what already exists for a website-driven launch.

### 6.10 Backend Changes
None beyond §5 (search) — `kynetic launch` is additive on the client only. If the existing `POST /v1/instances` response doesn't already include enough detail for the CLI to render the "Confirm" step (price, estimated cost) without a second round-trip, extend that endpoint's response shape (not its behavior) to include it.

### 6.11 Frontend Changes
None — this feature is explicitly CLI-only, consistent with "without opening the website."

### 6.12 CLI Changes
New `kynetic launch` command (interactive wizard + full non-interactive flag support); reuses the existing `connect` code path internally rather than duplicating PTY-session logic (§6.7's final step is a direct call into the same function `kynetic connect` itself calls).

### 6.13 Host Agent Changes
None — provisioning is already fully specified by the existing platform architecture; `kynetic launch` is a new way to *trigger* the existing flow, not a new flow.

### 6.14 Authentication
Reuses the existing `kynetic login` device-authorization session — `kynetic launch` requires an already-authenticated CLI session (per this feature's explicit precondition: "after the user has already logged in") and fails fast with a clear prompt to run `kynetic login` first if no valid session exists.

### 6.15 Progress UI
A single-line, updating progress indicator (spinner + elapsed time) through provisioning polling, matching the existing CLI's aesthetic for other long-running operations (no new UI framework, reuses whatever terminal-progress utility the CLI already uses elsewhere, e.g., for `kynetic cp` transfer progress).

### 6.16 Scheduler Interaction
None new — `kynetic launch`'s `POST /v1/instances` call goes through the exact same existing Scheduler ranking path as a website-initiated launch; the CLI may optionally pass the existing `--budget`/`--fastest` scheduler-hint flags (already specified in the platform's TDD) when the developer skips manual GPU selection in favor of goal-based selection.

### 6.17 Failure Recovery & Reconnect
If provisioning fails after launch, the CLI surfaces the existing failure reason (Scheduler fallback/retry already handles most transient host-provisioning failures server-side, per the existing platform's Failure Recovery table) and, on a hard failure, confirms the billing hold was released rather than leaving the developer uncertain. If the CLI process itself is interrupted after `POST /v1/instances` succeeds but before auto-connect completes (e.g., laptop sleeps), `kynetic launch` is idempotent-resumable: re-running `kynetic launch --resume <instance_id>` (or simply `kynetic connect <instance_id>`, printed as a fallback instruction) picks up exactly where the website-driven flow already allows.

### 6.18 Testing Strategy
End-to-end test: `kynetic launch` (non-interactive flags) → real instance provisioned → auto-connect succeeds → developer is in a working remote shell, timed against a target total elapsed budget. Interactive-wizard UX test (search-as-you-type responsiveness against §5's search latency target). Interruption-recovery test (kill CLI process mid-poll, verify `--resume`/manual `connect` recovers cleanly). Non-interactive scripting test (fully flagged invocation with zero prompts, suitable for CI/automation use by developers).

### 6.19 Security
No new security surface — reuses existing authenticated session, existing `Idempotency-Key` convention (preventing a double-launch from a retried CLI request), existing Gateway session authorization (§7.2 of the platform TDD, unchanged).

### 6.20 Observability
CLI-side: anonymous, opt-in timing telemetry (time-to-running, time-to-connected) to track the "under 60 seconds" and overall launch-to-shell targets in the field. Server-side: no new metrics beyond what §5 and the existing provisioning pipeline already emit — `kynetic launch` is just another client of already-instrumented endpoints.

### 6.21 Scaling Strategy
No new scaling concern — `kynetic launch` generates the same request shape and volume profile as any other launch path against already-scaled services (§5's search, existing provisioning/Scheduler).

### 6.22 Implementation Phases
**Phase 1:** Non-interactive `kynetic launch` (flags only, no wizard) wired to §5 search + existing provisioning + existing connect. **Phase 2:** Interactive wizard UX (search-as-you-type, selection prompts, progress UI). **Phase 3:** Interruption-recovery (`--resume`) and full scripting-flag coverage. **Phase 4:** Opt-in timing telemetry.

### 6.23 Acceptance Criteria
- [ ] `kynetic launch` (interactive) takes a developer from command to connected remote shell without opening a browser
- [ ] `kynetic launch` (non-interactive, fully flagged) succeeds in a scripted/CI context with zero prompts
- [ ] A provisioning failure never leaves a billing hold in place
- [ ] Interrupting the CLI mid-flow and resuming reaches the same running instance without duplicate provisioning (idempotency-key verified)

### 6.24 Complexity
Medium (orchestration-only, but UX polish and interruption-recovery correctness require careful testing).

### 6.25 Dependencies
§5 (Smart Search), existing `POST /v1/instances`, existing Scheduler, existing Gateway `connect` path, existing `kynetic login` device-auth session.

### 6.26 Future Improvements
Saved launch presets (`kynetic launch --preset my-training-rig`); multi-instance batch launch for parallel workloads; shell-completion-driven GPU/region selection.

---

## 7. Cross-Feature Summary

| Feature | New Service? | Primary Owner | Key Dependency |
|---|---|---|---|
| GPU Benchmark & Health Score | No | `reputation_pricing_service` + Host Agent | Existing Benchmark/Heartbeat Modules |
| Host Reputation | No | `reputation_pricing_service` | §1, existing wallet ledger |
| Verified Hosts | No | `auth_service` | Existing trust-tier/payment-linking |
| GPU Benchmark Database | No | `reputation_pricing_service` | §1 |
| Smart Search | No | `marketplace_service` | §1–§3, existing `listings` |
| One Command Launch | No | `kynetic` CLI | §5, existing provisioning/Scheduler/Gateway |

No new services are introduced anywhere in this plan — every feature is an additive extension of `auth_service`, `marketplace_service`, `reputation_pricing_service`, `provisioning_service`, the Tunnel Gateway, or the `kynetic` CLI, consistent with the instruction to reuse existing services and avoid overengineering.
