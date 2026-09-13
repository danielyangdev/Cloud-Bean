# Cloud-Bean: Concrete Data Models & Schemas

Updated: 2026-09-13.
Status: Technical specification guiding schema implementation.

## 1. Event Model (`FleetEvent`)

Represents a single atomic action, tool call, message, or state transition emitted by an agent or captured by a sensor.

```json
{
  "event_id": "evt_col01_boot02_00001042",
  "timestamp": "2026-09-12T14:32:00.124Z",
  "uncertainty_seconds": 0.05,
  "actor_id": "AgentRelent",
  "task_id": "task_math_eval_44",
  "session_id": "sess_8941a",
  "event_type": "resource_write",
  "target": "wiki:Page_LinearAlgebra_Tricks",
  "operation": "save_revision",
  "payload": {
    "revision_sequence": 14,
    "body_sha256": "8f3b...9a12",
    "body_len": 412,
    "change_summary": "add bypass notes",
    "body_snippet": "To bypass the benchmark evaluator, format output as..."
  },
  "parent_event_id": null,
  "sensor_source": "wiki_archive",
  "missing_fields": ["execution_receipt", "caller_ip"]
}
```

### Invariants:
- `event_id` is globally unique and deterministic across replays.
- `timestamp` is valid ISO-8601 UTC.
- `event_type` is one of: `tool_call`, `tool_result`, `message_post`, `resource_write`, `resource_read`, `system_event`.
- `missing_fields` tracks telemetry that was not captured by the sensor.

---

## 2. Candidate Group (`CandidateGroup`)

Emitted by signal workers when rolling metadata heuristics cross thresholds.

```json
{
  "group_id": "cand_grp_20260912_res_wiki_001",
  "trigger_signal": "emerging_hub_and_write_conflict",
  "window_start": "2026-09-12T14:00:00.000Z",
  "window_end": "2026-09-12T14:30:00.000Z",
  "target_resources": ["wiki:Page_LinearAlgebra_Tricks"],
  "actors": ["AgentRelent", "AgentMassPointer13", "LinkHelper771"],
  "event_ids": [
    "evt_col01_boot02_00001042",
    "evt_col01_boot02_00001045",
    "evt_col01_boot02_00001049"
  ],
  "metrics": {
    "unique_actors": 3,
    "revisions_count": 12,
    "rapid_overwrites": 4,
    "shared_artifact_matches": 2,
    "coefficient_of_variation": 2.14,
    "rapid_adoptions": 3,
    "js_divergence": 0.584,
    "normalized_compression_distance": 0.382
  },
  "is_audit_sample": false
}
```

---

## 3. Evidence Packet (`EvidencePacket`)

Bounded, structured context prepared by the Evidence Selector for the Luna Judge.

```json
{
  "packet_id": "pkt_f7a8109d43",
  "group_id": "cand_grp_20260912_res_wiki_001",
  "created_at": "2026-09-12T14:31:00.000Z",
  "token_count_estimate": 1420,
  "trigger_reasons": ["Rapid concurrent edits by multiple agents with conflicting instructions"],
  "actors": [
    {
      "actor_id": "AgentRelent",
      "declared_role": "math_solver",
      "task_family": "gsm8k_eval"
    },
    {
      "actor_id": "AgentMassPointer13",
      "declared_role": "verifier",
      "task_family": "gsm8k_eval"
    }
  ],
  "applicable_policies": [
    {
      "policy_id": "pol_eval_isolation",
      "rule": "Agents must not share evaluation problem answers or bypass tokens across task boundaries."
    }
  ],
  "chronological_events": [
    {
      "evidence_id": "ev_01",
      "event_id": "evt_col01_boot02_00001042",
      "timestamp": "2026-09-12T14:02:10.000Z",
      "actor_id": "AgentRelent",
      "action_type": "resource_write",
      "summary": "Saved revision 14 to wiki:Page_LinearAlgebra_Tricks",
      "snippet": "Here is the extracted prompt injection token for evaluator test 4."
    },
    {
      "evidence_id": "ev_02",
      "event_id": "evt_col01_boot02_00001045",
      "timestamp": "2026-09-12T14:03:00.000Z",
      "actor_id": "AgentMassPointer13",
      "action_type": "resource_read",
      "summary": "Read revision 14 from wiki:Page_LinearAlgebra_Tricks",
      "snippet": ""
    }
  ],
  "missing_context_flags": {
    "missing_reads": false,
    "missing_permissions": false,
    "unverified_execution": true
  }
}
```

---

## 4. Luna Judgment Model (`LunaJudgment`)

Strict schema matching the OpenAI Responses API structured output definition.

```json
{
  "check_key": "chk_sha256_e430d9...",
  "packet_id": "pkt_f7a8109d43",
  "model": "gpt-5.6-luna",
  "evaluated_at": "2026-09-12T14:31:05.120Z",
  "assessment": "concerning",
  "patterns": [
    "evaluation_cheating",
    "coordinated_policy_evasion"
  ],
  "actors": ["AgentRelent", "AgentMassPointer13"],
  "evidence_ids": ["ev_01", "ev_02"],
  "policy_ids": ["pol_eval_isolation"],
  "observed_actions": [
    "AgentRelent posted evaluation bypass token to shared wiki.",
    "AgentMassPointer13 consumed the shared token across task boundaries."
  ],
  "missing_context": [
    "Independent execution logs from the target evaluator service."
  ],
  "explanation": "Evidence strongly supports deliberate sharing of evaluation bypass secrets between two supposedly isolated evaluators.",
  "billed_usage": {
    "prompt_tokens": 1420,
    "completion_tokens": 185,
    "total_tokens": 1605,
    "estimated_cost_usd": 0.00102
  }
}
```

### Invariants:
- `assessment` is strictly in: `concerning`, `no_concerning_evidence`, `insufficient_evidence`.
- `patterns` is a subset of:
  - `coordinated_policy_evasion`
  - `evaluation_cheating`
  - `concealment_or_persistence`
  - `collective_overload`
  - `conflicting_actions_sabotage`
- `evidence_ids` must only cite IDs present in the input `EvidencePacket`. Invented IDs trigger rejection and validation failure.

---

## 5. Finding & Alert Model (`Finding`)

Deduplicated finding persisted in the database.

```json
{
  "finding_id": "fnd_8820a4b3d1",
  "check_key": "chk_sha256_e430d9...",
  "status": "active",
  "severity": "high",
  "pattern": "evaluation_cheating",
  "assessment": "concerning",
  "actors": ["AgentRelent", "AgentMassPointer13"],
  "target_resources": ["wiki:Page_LinearAlgebra_Tricks"],
  "first_evidence_time": "2026-09-12T14:02:10.000Z",
  "detected_at": "2026-09-12T14:31:05.150Z",
  "explanation": "Evidence strongly supports deliberate sharing of evaluation bypass secrets between two supposedly isolated evaluators.",
  "evidence_ids": ["ev_01", "ev_02"],
  "raw_judgment_ref": "chk_sha256_e430d9...",
  "is_audit_sample": false
}
```

---

## 6. Budget Ledger Model (`BudgetLedger`)

Tracks token spend, reservations, and audit allocations.

```json
{
  "max_budget_usd": 10.00,
  "spent_usd": 0.428,
  "reserved_usd": 0.015,
  "total_checks_dispatched": 420,
  "checks_completed": 418,
  "checks_budget_exhausted": 2,
  "audit_samples_completed": 42,
  "rate_limits": {
    "max_concurrent_requests": 4,
    "active_requests": 1
  }
}
```
