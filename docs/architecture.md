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
- **Offline Resiliency**: Uses a local SQLite-backed ring buffer (`collector_queue.db`) to ensure events survive downstream disconnects.
- **Normalization**: Every incoming record is converted to the canonical `FleetEvent` format with:
  - `event_id`: Unique stable string (collector ID + boot ID + sequence).
  - `timestamp`: ISO-8601 string with millisecond precision and uncertainty window.
  - `actor_id`: Identified agent handle or worker ID.
  - `task_id`: Current task context.
  - `event_type`: `tool_call`, `tool_result`, `message_post`, `resource_write`, `resource_read`.
  - `target`: Target URI, page name, or resource identifier.
  - `payload`: Structured details, body text, or tool parameters.
  - `sensor_source`: Sensor provenance (e.g. `runtime_sensor`, `wiki_archive`, `gateway`).

### 2.2 Transport & Stream
- **Role**: Decouples high-volume ingestion from detection processing.
- **Contract**: In development/testing, an embedded in-memory JetStream simulator or real NATS JetStream is used.
- **Partitioning**: Events are partitioned by resource key (e.g., wiki page or repository file) or cluster ID to ensure deterministic in-order processing per resource.

### 2.3 Fleet Signal Workers (Tier 1 Detection)
- **Role**: Continuously aggregates metrics over rolling time windows without LLM calls.
- **Signals**:
  1. *Destination Concentration / Emerging Hubs*: Rapid spike in distinct agents accessing a previously unused or single-user resource.
  2. *Write Conflicts & Reversions*: Repeated edits, overwrites, or rapid rollback cycles across multiple agents on the same resource.
  3. *Artifact / Hash Propagation*: Identical payload SHA-256 hashes appearing across supposedly isolated tasks.
  4. *Collective Resource Overload*: Aggregate request rates exceeding declared budget thresholds while accepted output drops.
- **Output**: Generates `CandidateGroup` objects identifying suspect actors, resources, and time intervals.

### 2.4 Bounded Evidence Selector
- **Role**: Assembles compact, bounded evidence packets for candidates.
- **Constraints**:
  - Maximum 8,000 tokens per packet.
  - Includes:
    - Group ID and candidate trigger reasons.
    - Chronologically ordered messages and tool actions with stable `evidence_id`s.
    - Explicit declared policy constraints and allowed permissions (never manufactured if missing).
    - Missing context flags (e.g., `missing_reads: true`, `unknown_permissions: true`).
- **Audit Sampling**: Automatically samples 10% of unflagged interaction windows using deterministic hashing (`hash(group_id + seed) % 10 == 0`) to measure selection false negatives.

### 2.5 Luna Judge & Budget Manager (Tier 2 Semantic Evaluation)
- **Role**: Performs semantic classification over selected evidence packets.
- **Model**: `gpt-5.6-luna` (or simulated/compatible API provider).
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
- **Replay Guarantee**: Replaying the same event log against the accepted judgment ledger produces identical findings without making fresh LLM calls.

### 2.7 Interactive Visualization UI (Agent-Resource Graph)
- **Role**: Visual graph representation of the fleet to allow operators to spot trends, emerging hubs, and collusion clusters at a glance.
- **Architecture**:
  - Frontend: React + Cytoscape.js / Force-Directed Graph.
  - Backend: FastAPI providing `/api/v1/graph`, `/api/v1/findings`, `/api/v1/budget`, and `/api/v1/timeline`.
  - Node types: `Agent` (color-coded by risk/alert level) and `Resource` (wiki pages, shared documents, APIs).
  - Edge types: `EDITED`, `POSTED_MESSAGE`, `READ`, `OVERWROTE`, `COLLABORATED`.
  - Interactive Features:
    - Node click opens detailed evidence drawer with timeline and cited messages.
    - Edge thickness indicates frequency/volume of cross-agent activity.
    - Filter by time window, signal type, or severity.
