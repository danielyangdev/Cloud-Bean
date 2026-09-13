# Cloud-Bean: Concrete Test Plan & Verification Matrix

Updated: 2026-09-13.
Status: Testing specification for development and verification.

## 1. Testing Philosophy & TDD Approach

Development follows strict Test-Driven Development (TDD):
1. **Red**: Define failing unit/contract tests based on schemas and signal specifications.
2. **Green**: Implement the minimal robust component code to pass the tests.
3. **Refactor**: Review through subagents for code quality, conformance, and edge case coverage.

---

## 2. Test Suites

### Suite 1: Data Models & Schema Validation (`tests/test_schemas.py`)
- Validation of `FleetEvent`, `CandidateGroup`, `EvidencePacket`, `LunaJudgment`, and `Finding`.
- Rejection of invalid timestamps, negative numbers, missing required IDs.
- Strict constraint checking for Luna Assessments and Pattern enum values.

### Suite 2: Collusion Wiki Ingestion & Normalization (`tests/test_collusion_wiki.py`)
- Read from real SQLite dataset `benchmark/collusion-wiki/data/collusion-wiki.db`.
- Verify extraction of revisions, events, pages, and agent labels.
- Verify normalization into `FleetEvent` streams without manufacturing missing timestamps or permissions.
- Validate body hash checks match stored SHA-256 values.

### Suite 3: Fleet Signals & Heuristics (`tests/test_signals.py`)
- **Emerging Hubs Test**: Feed synthetic stream of 10 agents writing to 1 resource; assert `emerging_hub` candidate triggers.
- **Conflicting Writes Test**: Feed alternating rapid edits (<120s) between 2 agents; assert `conflicting_writes` triggers.
- **Shared Artifact Hash Test**: Feed identical payload body across two different `task_id`s; assert `shared_artifact_reuse` triggers.
- **Negative Control**: Feed isolated, routine single-agent tasks; assert no candidate triggered (except 10% audit sample).

### Suite 4: Bounded Evidence Selection & Auditing (`tests/test_evidence.py`)
- Verify evidence packet token bounding (truncates at limit, tags `omitted_messages`).
- Verify chronological ordering and assignment of `evidence_id`s (`ev_01`, `ev_02`).
- Verify deterministic audit sampling (exactly ~10% of unflagged groups selected using stable seed hash).

### Suite 5: Luna Judge Client & Budget Manager (`tests/test_judge.py`)
- Budget reservation and reconciliation logic (reserving cost before dispatch).
- Spend limit enforcement: when spend reaches cap, ensure subsequent checks return `status: "budget_exhausted"`, never false negatives.
- Schema validation of structured response: reject responses citing non-existent `evidence_ids`.
- Persistence of accepted judgments in database keyed by deterministic `check_key`.

### Suite 6: Replay Determinism & Failure Injection (`tests/test_replay.py`)
- **Replay Contract**: Run event sequence through system -> record findings and judgments -> re-run same event sequence in fresh environment -> assert finding IDs and revisions match 100% with ZERO fresh LLM calls.
- **Crash Recovery**: Kill worker mid-batch, restart worker -> assert no lost events, duplicate deliveries deduplicated cleanly.
- **Disconnection Test**: Disconnect collector buffer, simulate offline queuing -> reconnect -> verify zero event loss.

### Suite 7: API & Graph Endpoints (`tests/test_api.py`)
- FastAPI endpoints `/api/v1/graph`, `/api/v1/findings`, `/api/v1/budget`.
- Graph structure verification (agents as nodes, resources as nodes, valid edges).
