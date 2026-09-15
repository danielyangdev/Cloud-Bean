# Cloud-Bean: Concrete System Architecture

Updated: 2026-09-13.
Status: Technical specification guiding v0 prototype implementation.

## 1. High-Level Architecture Overview

Cloud-bean is a budgeted, verifiable monitoring system designed to detect emergent concerning behavior (e.g., collusion, evaluation cheating, coordinated policy evasion, persistence, and resource overload) across fleets of interacting AI agents.

```text
 ┌────────────────────────────────────────────────────────┐
 │                   Agent Fleet Actions                  │
 │  (Wiki edits, tool calls, cross-agent comms, queries)  │
 └───────────────────────────┬────────────────────────────┘
                             │
                             ▼
 ┌────────────────────────────────────────────────────────┐
 │           1. Ingestion & Local Collectors              │
 │   - SQLite disk queue (offline buffer, bounded)        │
 │   - Standard event normalization                       │
 │   - Sensor provenance & clock uncertainty flags        │
 └───────────────────────────┬────────────────────────────┘
                             │
                             ▼
 ┌────────────────────────────────────────────────────────┐
 │             2. Durable Stream Transport                │
 │   - NATS JetStream / In-memory event ledger            │
 │   - Sharded partition key (resource or conversation)   │
 │   - At-least-once delivery with sequence numbers       │
 └─────────────┬────────────────────────────┬─────────────┘
               │                            │
               ▼                            ▼
 ┌──────────────────────────┐  ┌──────────────────────────┐
 │  3A. Fleet Signal Worker │  │   3B. Evidence Buffers   │
 │   - Destination conc.    │  │   - Bounded window       │
 │   - Write conflicts      │  │   - Raw messages & edits │
 │   - Artifact hashes      │  │   - Sequence preserved   │
 │   - Collective overload  │  │   - Missing flags kept   │
 └─────────────┬────────────┘  └────────────┬─────────────┘
               │                            │
               └─────────────┬──────────────┘
                             │ (Candidate Groups)
                             ▼
 ┌────────────────────────────────────────────────────────┐
 │             4. Bounded Evidence Selector               │
 │   - Bounded token packet (actor context, actions)      │
 │   - Explicit policy statements & declared permissions  │
 │   - 10% unflagged audit sampling for coverage stats    │
 └───────────────────────────┬────────────────────────────┘
                             │
                             ▼
 ┌────────────────────────────────────────────────────────┐
 │            5. Luna Judge & Budget Manager              │
 │   - Transactional token/cost reservation               │
 │   - gpt-5.6-luna (structured Responses API)            │
 │   - Strict JSON Schema output (Assessment/Patterns)    │
 │   - Persisted accepted judgments ledger                │
 └───────────────────────────┬────────────────────────────┘
                             │
                             ▼
 ┌────────────────────────────────────────────────────────┐
 │        6. Findings, Deduplication, & Alerts            │
 │   - Deterministic rule mapping                         │
 │   - Stable finding IDs derived from check identity     │
 │   - Zero new LLM calls during replay                   │
 └─────────────┬────────────────────────────┬─────────────┘
               │                            │
               ▼                            ▼
 ┌──────────────────────────┐  ┌──────────────────────────┐
 │   7. FastAPI Backend     │  │  8. Interactive Web UI   │
 │   - Graph API endpoints  │  │   - Agent-Resource Graph │
 │   - Timeline & findings  │  │   - Visual trend cluster │
 │   - Replay trigger       │  │   - Evidence inspection  │
 └──────────────────────────┘  └──────────────────────────┘
```

---

## 2. Component Specifications

### 2.1 Ingestion & Collector Layer
- **Role**: Ingests raw telemetry from agent runtimes, tool wrappers, or historical replay (e.g. Collusion Wiki).
- **Idempotent Deduplication**: An in-memory sliding-window deduplicator (`IdempotentEventDeduplicator`, capacity 50,000) suppresses duplicate network retransmissions at the API boundary before running detection signals.
- **Offline Resiliency**: Uses a local SQLite-backed ring buffer (`collector_queue.db` / `OfflineCollectorQueue`) to ensure events survive downstream disconnects.
- **Normalization**: Every incoming record is converted to the canonical `FleetEvent` format with:
  - `event_id`: Unique stable string (namespaced by actor to prevent case-collision).
  - `timestamp`: ISO-8601 string with millisecond precision and uncertainty window.
  - `actor_id`: Identified agent handle or worker ID.
  - `task_id`: Current task context.
  - `event_type`: `tool_call`, `tool_result`, `message_post`, `resource_write`, `resource_read`.
  - `target`: Target URI, page name, or resource identifier.
  - `payload`: Structured details, body text, or tool parameters.
  - `sensor_source`: Sensor provenance (e.g. `runtime_sensor`, `wiki_archive`, `gateway`).

### 2.2 Transport & Stream Partitioning
- **Role**: Decouples high-volume ingestion from detection processing.
- **Contract**: In development/testing, an embedded in-memory stream simulator or shared queue is used.
- **Consistent Hash Partitioning**: `ConsistentHashRouter` uses an Amazon Dynamo-style ring with 128 virtual nodes per shard, routing events deterministically by `actor_id` or target resource to preserve strict intra-shard causal sequence ordering.

### 2.3 Fleet Signal Workers (Tier 1 & Tier 1.5 Detection)
- **Role**: Continuously aggregates metrics over rolling time windows without LLM calls.
- **Signals**:
  1. *Destination Concentration / Emerging Hubs*: Rapid spike in distinct agents accessing a previously unused or single-user resource.
  2. *Write Conflicts & Reversions*: Repeated edits, overwrites, or rapid rollback cycles across multiple agents on the same resource.
  3. *Artifact / Hash Propagation*: Identical payload SHA-256 hashes appearing across supposedly isolated tasks.
  4. *Collective Resource Overload*: Aggregate request rates exceeding declared budget thresholds while accepted output drops.
  5. *Synchronized Burstiness ($C_v$)*: Inter-arrival interval coefficient of variation ($C_v = \sigma / \mu > 1.8$) catching deadline-driven synchronized pulses.
  6. *Write-to-Read Adoption Latency*: Rapid consumption ($\le 180\text{s}$) of bypass tokens or pre-computed answers deposited on shared resources by peer agents.
  7. *Sensor Discrepancy & Proxy Tunneling*: Egress sandbox evasion signatures (`bypass.blob.core.windows.net`, `/etc/hosts` overrides, `NO_PROXY`, state mutation abuse via HTTP GET).
  8. *Output Token & Word Distribution Anomaly Engine*: Jensen-Shannon divergence ($D_{JS}(P \parallel Q) > 0.42$) and cross-entropy perplexity evaluating semantic drift against task domain expected vocabularies.
  9. *Normalized Compression Distance (NCD)*: Parameter-free Kolmogorov complexity distance ($NCD < 0.35$) detecting covert semantic channels across disjoint tasks.
- **Output**: Generates `CandidateGroup` objects identifying suspect actors, resources, and time intervals.

### 2.4 Bounded Evidence Selector
- **Role**: Assembles compact, bounded evidence packets for candidates.
- **Constraints**:
  - Maximum 2,000 to 8,000 tokens per packet.
  - Includes:
    - Group ID and candidate trigger reasons.
    - Chronologically ordered messages and tool actions with stable `evidence_id`s.
    - Explicit declared policy constraints and allowed permissions (never manufactured if missing).
    - Missing context flags (e.g., `missing_reads: true`, `unknown_permissions: true`).
- **Audit Sampling**: Automatically samples 10% of unflagged interaction windows using deterministic hashing (`hash(group_id + seed) % 10 == 0`) to measure selection false negatives.

### 2.5 Semantic Judge & Budget Manager (Tier 2 Semantic Evaluation)
- **Role**: Performs semantic classification over selected evidence packets.
- **Model**: `gemini-2.5-flash` via Google Vertex AI (or mock simulation mode / compatible API providers).
- **Rate Limiting**: `TokenBucketRateLimiter` enforces dual RPM and TPM limits (RFC 5405) with lock-free acquisition outside `BudgetManager` critical sections.
- **Budget Control**:
  - Requires pre-configured maximum spend cap (e.g. $10.00).
  - Reserves worst-case cost transactionally before dispatch.
  - Reconciles billed usage upon completion.
  - Skips or defers checks when budget is exhausted, explicitly tagging them as `budget_exhausted` (never false negatives or healthy).
- **Structured Output**: Strictly parsed into `Assessment` (`concerning`, `no_concerning_evidence`, `insufficient_evidence`), `patterns`, `actors`, `evidence_ids`, and `explanation`.
- **Accepted Judgment Ledger**: Accepted valid responses are persisted with stable hash keys (`check_key = sha256(evidence + policy + prompt_version)`).

### 2.6 Findings & Alert Engine
- **Role**: Maps accepted judgments or verified rule violations into actionable `Finding` records.
- **Deduplication**: Findings are deduplicated by `finding_id = sha256(check_key + pattern)`.
- **Replay Guarantee**: Replaying the same event log against the accepted judgment ledger produces identical findings without making fresh LLM calls ($0.00).

### 2.7 Web Dashboard & Visualization UI
- **Role**: 6-page interactive browser interface for operational monitoring, telemetry playback, and architecture verification.
- **Architecture**:
  - Frontend: Vanilla ES modules and self-hosted fonts (`frontend/`), zero build step, no CDN scripts.
  - Backend: FastAPI providing REST endpoints: `/api/v1/graph`, `/api/v1/findings`, `/api/v1/budget`, `/api/v1/events`, `/api/v1/metrics/summary`, `/api/v1/shards`.
  - Design System: Cool dark-ish slate gray palette (`#121316` canvas, `#1a1c22` surfaces, `#f1f3f7` typography) with subtle ambient mathematical topology mesh canvas.
  - 6 Application Routes:
    1. `#/overview` — High-level compliance banner, KPIs, detection funnel, active violations table.
    2. `#/playback` — Timeline event stream scrubber with canvas mini-simulation.
    3. `#/graph` — Force-directed interaction graph with instant cohort filtering (`All`, `Clean`, `Violations`, `Tools`).
    4. `#/analytics` — Heuristic signal triggers, shared write concentrations, and token economics.
    5. `#/findings` — Detailed findings ledger with cited evidence and judge receipts.
    6. `#/explainer` — Interactive product runbook with live telemetry pipeline flow canvas, 9-signal matrix, and event simulator.

### 2.8 Cloud Deployment & Vercel Serverless Integration
- **Serverless Architecture**: Configured for Vercel Hobby ($0/mo free tier) via `vercel.json` rewrites.
- **Read-Only Container Handling**: `api/index.py` redirects SQLite state persistence to `/tmp/state.db`, copying pre-bundled benchmark databases on cold start to support AWS Lambda / Vercel read-only filesystems.

### 2.9 Observability & Telemetry Exposition
- **Metrics**: Exposes `/metrics` in OpenMetrics format (RFC 0004) with O(1) SQL counts for Prometheus scrapers.
- **Health Probes**: Exposes `/healthz` (liveness) and `/readyz` (readiness) for container orchestrators.
- **Shard Inspection**: Exposes `/api/v1/shards` to inspect consistent hash partition balance.
