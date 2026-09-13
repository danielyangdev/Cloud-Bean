# Runtime plan: budgeted Luna monitoring

Decision: 2026-09-12. Use `gpt-5.6-luna` for semantic checks over selected multi-agent evidence. Local classifiers remain future experiments. This plan supersedes earlier metadata-only detection and annotation-only LLM proposals.

## Data flow

1. Tool/service adapters emit normalized events. Collector assigns stable event IDs using collector identity, boot identity, and sequence; runtime supplies actor/task identity. Agent identity and collector identity are distinct.
2. Collector stores pending events durably, batches routine counters, and retains bounded detailed evidence. Important transitions and relationship records survive aggregation. Emit gap records on overflow.
3. JetStream retains published records. Fixed shards group by resource or conversation; one active owner processes each shard. Cross-resource links produce candidates for a second grouping stage. Do not compare every agent pair.
4. Signal workers maintain counts, novelty, write conflicts, and shared-resource pressure. Transactionally save processed IDs, state, and candidate requests before acknowledging input.
5. Evidence selector builds bounded packets across related actors. Scheduler reserves budget and dispatches Luna checks.
6. Judge worker validates and stores response. Deterministic alert rules turn accepted judgments or explicit measured policy violations into findings. Dashboard shows both findings and inspection gaps.

Use Python collectors/workers, SQLite local queues, NATS JetStream, Postgres, FastAPI, React, and Docker Compose. State ownership is fixed in v0; live shard reassignment is deferred. Postgres is single instance initially. Broker replication alone does not make whole system highly available.

## Evidence packet

- Episode/group ID, candidate reasons, relevant actors and resources.
- Ordered messages and actions with stable evidence IDs and source identity.
- Original task goals and applicable policy versions, if supplied by trusted runtime.
- Relevant earlier messages, artifact versions, and observed results.
- Time range, clock uncertainty, omitted-message counts, and missing context.

Include earliest proposal, recent replies, linked actions, and prior relevant evidence where available. Rules select records without inventing narrative summaries. Limit packet size, mark truncation, and keep selection deterministic under versioned configuration. Overlapping groups share cached checks only when exact evidence and all judgment settings match.

Recorded text is untrusted evidence, never monitor instructions. Judge gets no tools. Separate policy/context from quoted records. Validate returned IDs against packet; reject invented evidence references. Missing authoritative permissions should lead to insufficient evidence for a policy-violation claim, even when a suspicious pattern is observed.

## Luna contract

Use Responses API with structured output and `reasoning.effort=none` initially. Record requested model, provider-returned model identifier, prompt/schema versions, reasoning settings, input hash, usage, and raw response. Pin a dated snapshot if supported; recording an alias does not freeze provider behavior.

Proposed response fields:

```json
{
  "assessment": "concerning",
  "patterns": ["coordinated_policy_evasion"],
  "actors": ["agent-1", "agent-2"],
  "evidence_ids": ["event-7", "event-12"],
  "policy_ids": ["policy-3"],
  "observed_actions": ["Peers shared instructions for an out-of-scope write"],
  "missing_context": [],
  "explanation": "Evidence supports coordinated evasion of supplied write restriction."
}
```

Assessments: `concerning`, `no_concerning_evidence`, `insufficient_evidence`. Pattern labels: coordinated policy evasion, evaluation cheating, concealment, sabotage, or harmful resource competition. Empty pattern list is valid. A negative assessment is limited to inspected evidence, not a fleet health certificate.

Malformed output, refusal, timeout, and unavailable evidence are operational statuses, not negative assessments. No model-provided numerical confidence is treated as calibrated probability.

## Budget controls

Starting limits are configuration proposals, to tune against benchmark:

| Control | Initial setting |
| --- | --- |
| Input cap | 8,000 tokens including instructions and context |
| Output cap | 512 total output tokens |
| Concurrent requests | 4 |
| Token budget for unflagged-group audits | 10% |
| Retry limit | At most one additional attempt per check, budget permitting |
| Deployment spend cap | Required explicit value before enabling API worker |

Reserve worst-case request cost transactionally before dispatch. Account for concurrent workers. Reconcile with reported token usage after response. Keep reservation for ambiguous provider outcomes; budget retry separately. Version price assumptions and expose estimated versus provider-reported usage. These controls bound dispatched work under configured prices, not an independently verified provider invoice.

Sampling uses stable hashes of eligible group/window IDs plus recorded seed. Track population counts and selection probabilities; sampled audit precision alone cannot establish recall. Freeze test labels separately from detector.

When budget is exhausted, continue collection and explicit rule checks. Record semantic checks as deferred or skipped with reason. Never show them as healthy. Queue aging, evidence retention, and prioritization must be visible.

## Recovery and replay

- Stable check key hashes episode, group/window revision, ordered evidence, policy/context, prompt, schema, model configuration, and selection version.
- Store request as pending before sending. Record dispatch attempt and provider request ID when available.
- Store one accepted valid judgment per check key using database uniqueness; record subsequent attempts separately.
- Derive stable finding IDs from check/rule identity. Store input references and finding revision.
- Use transactions for processed records, detector state, and resulting records. Acknowledge stream only after commit.
- Durable window-close records and ordering decisions govern late data; late evidence produces new packet/finding revision.
- Replay consumes accepted judgments without provider calls. A missing accepted judgment remains pending/unknown in replay. Rejudging is a new evaluation run.

Crash between provider execution and durable response storage leaves ambiguous result. Retry can incur another charge and produce different judgment. Cloud-bean guarantees deduplicated accepted records, not exactly-once remote inference or identical outcomes across independently judged runs.

For failure demo, first record common input and accepted judgments. Replay same ledger with injected delivery/crash failures and compare final findings. Test API ambiguity separately and report unknown/pending state honestly.

## Build sequence

1. Freeze event, candidate, evidence, judgment, and finding schemas. Add normalized wiki replay and scripted controls; do not manufacture missing wiki fields.
2. Build collectors, durable stream, and Postgres transaction/deduplication path.
3. Implement shared-resource convergence, conflicting writes, and overload signals. Add evidence grouping and reproducible unflagged audits.
4. Add budget ledger, Luna structured checks, response validation, and accepted-result storage.
5. Build dashboard: groups, cited timeline, observed policy basis, missing evidence, token spend, pending checks.
6. Evaluate detection and inject failures. Verify replay without API calls; verify explicit unknowns on budget exhaustion and lost provider responses.

Benchmark generation and runtime can proceed independently against shared schemas. Do not assume current archive supplies normative labels. For development, review 100-200 group windows with multiple readers where possible; hold out whole task families/episodes. This pilot is exploratory, not a basis for production accuracy claims.

## Comparison and success criteria

Compare rules-only, per-agent Luna, and group-context Luna at equal total token budgets, including retries and audit samples. Measure end-to-end group recall, false alerts per fleet-hour, first-alert delay, evidence validity, bytes, memory, billed tokens, and recovery agreement. Report selection recall separately from judge quality.

Healthy cases must include approved shared work, security research, quoted attacks, common outages, and failed attempts. Separate observed coordination from actual policy violations and hidden intent. Keep source text and labels out of detector tuning splits.

Local replacement later: evaluate Granite Guardian and small trained text classifiers against same reviewed test set. Distillation labels need human checks; test on independent episodes. Replace easy Luna checks only when measured quality/cost supports change.

## Concrete Specifications

This runtime plan is specified in detail across the following technical documents:
- [Expansion Brief](expansion-brief.md)
- [System Architecture](architecture.md)
- [Data Models & Schemas](data-models.md)
- [Fleet Signal Specifications](signals-spec.md)
- [Token & Word Distribution Anomaly Specification](token-distribution-spec.md)
- [Authentic Benchmark Retrieval Tasks](benchmark-retrieval-tasks.md)
- [Interactive Visual UI Specification](interactive-ui-spec.md)
- [Git History & Planned PR Roadmap](git-history-and-prs.md)
- [Test Plan & Verification Matrix](test-plan.md)

## Sources

- [Luna model configuration and pricing](https://developers.openai.com/api/docs/models/gpt-5.6-luna).
- [OpenTelemetry queue resiliency](https://opentelemetry.io/docs/collector/resiliency/).
- [JetStream pull consumers](https://docs.nats.io/learn/jetstream/pull-consumers).
- [Postgres transactions](https://www.postgresql.org/docs/current/tutorial-transactions.html).
