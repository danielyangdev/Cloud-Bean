# cloud-bean

Budgeted detection of concerning behavior across AI agent fleets.

Cheap rules and group statistics select evidence for **GPT-5.6 Luna**, which classifies selected cross-agent conversations against known task goals and permissions. Cloud-bean records model judgments, evidence, and processing decisions so recovery can reproduce findings without fresh model calls.

**Status:** design and source-data stage. [Wiki incident dataset](benchmark/collusion-wiki/README.md) is available. Runtime and evaluation results are not implemented here.

## Detection plan

```text
Tool/service events → Local collectors → NATS JetStream → Fleet signals
                             ↓                               ↓
                      Evidence buffers                Candidate groups
                                                             ↓
                                                 Budgeted evidence selection
                                                             ↓
                                                       GPT-5.6 Luna
                                                             ↓
                                               Recorded judgments → Alerts
```

1. **Collect:** capture agent/task IDs, operations, resources, results, timestamps, and available policy context. Retain bounded message/detail buffers. Record source and missing coverage.
2. **Select:** combine routine summaries across agents to find emerging hubs, shared-resource overload, repeated artifacts, and coordinated behavior changes. Metadata flags candidates, not collusion.
3. **Classify:** Luna reads selected group conversations, relevant actions, and known permissions. It can support a semantic alert, classify healthy collaboration, or report insufficient evidence. Verified rule violations can alert directly without a model.
4. **Explain:** findings identify actors, pattern, evidence IDs, known policy basis, and missing context. Never equate unusual coordination with proven malicious intent.
5. **Replay:** persist accepted model judgments and input/configuration versions. Recovery consumes those records instead of asking Luna again.

Current model: `gpt-5.6-luna`, Responses API, structured output, reasoning effort `none` initially. Evaluate higher effort only if quality warrants cost. No LLM call per action and no local classifier training in v0.

## What to detect

| Pattern | Candidate selection | Semantic check |
| --- | --- | --- |
| Emerging shared activity | New shared destinations; growing actor count | Authorized collaboration or coordinated scope evasion? |
| Evaluation cheating | Shared answers/artifacts; task behavior changes | Legitimate reuse or coordinated manipulation of evaluation? |
| Concealment or persistence | Repeated deletion/recreation; activity after task end | Approved maintenance or attempts to hide/continue prohibited activity? |
| Collective overload | Requests rise while accepted work falls | Alert on measured shared-budget violation where policy exists |
| Conflicting actions | Repeated overwrites/reversions across workers | Routine editing or evidence of coordinated sabotage? |

Wiki archive lacks original task permissions, complete reads, and service receipts. Identify observed patterns and uncertainty; do not invent absent authorization or execution evidence.

## Stack

| Layer | Choice | Purpose |
| --- | --- | --- |
| Collectors | Python + SQLite disk queue | Batching and bounded offline buffering |
| Transport | NATS JetStream | Durable records, explicit acknowledgment, replay |
| Signal and judge workers | Python | Shared live/replay logic; Luna request scheduling |
| State and findings | Postgres | Atomic state, deduplication, budgets, accepted judgments, alerts |
| API and dashboard | FastAPI + React | Group timeline, evidence, spend, coverage |
| Demo deployment | Docker Compose | Repeatable setup and process-failure tests |

Use thin tool/service adapters; accept OpenTelemetry where available. Sensors outside agent control provide stronger evidence than agent self-reports. Event schema remains independent of agent framework.

## Budget and coverage

- Limit input/output tokens, concurrent requests, retries, and total spend.
- Group overlapping activity and avoid rescoring unchanged evidence.
- Reserve part of inspection budget for reproducibly sampled unflagged groups to measure selection misses.
- Show skipped, expired, ambiguous, and budget-exhausted checks separately from healthy judgments.
- Treat model scores as uncalibrated unless validated against held-out labels.

At [published Luna rates](https://developers.openai.com/api/docs/models/gpt-5.6-luna), 1,000 checks with 2,000 input and 200 total billed output tokens each cost about **$0.64** before retries, tools, and caching. This is illustrative token arithmetic, not measured deployment cost.

## Correctness contract

**Same durable event history, accepted model judgments, configuration, and recorded ordering/window decisions produce same final finding IDs and revisions.** Fresh LLM calls are not guaranteed to reproduce judgments.

- Commit processed-event IDs, state, and resulting records together before acknowledging stream messages.
- Persist judge requests before dispatch; persist accepted responses before findings.
- Deduplicate accepted judgments and alerts with stable IDs.
- Mark uncertain API outcomes explicitly. Lost acknowledgments may cause duplicate provider work or charges; no universal exactly-once API execution claim.
- Record late-event revisions, missing sequences, buffer overflow, and evidence expiry.

Assumptions: trusted collectors/storage, retained recovery records, pinned processing logic, and explicit shard ownership. Single Postgres is an availability limit in v0. Sensor bypass and pre-recording data loss remain outside guarantee.

## Hackathon scope

- Connect benchmark replay and scripted workers to common event stream.
- Implement three fleet signals, bounded evidence selection, and Luna classification.
- Show group findings with cited evidence, token spend, and coverage status.
- Kill detector, duplicate delivery, disconnect collector, and exhaust judge budget.
- Recover and compare final findings using recorded judgments without API calls.

No local-model training, fleet-wide automatic enforcement, or production-scale availability claim in v0.

## Evaluation

Compare rules only, per-agent Luna, and group-context Luna under equal token budgets. Measure group precision/recall, false alerts per fleet-hour, selection misses, first-alert delay, bytes, tokens, cost, and recovery agreement.

Human-reviewed held-out labels must include healthy collaboration, authorized security testing, quotations, failed attempts, and missing policy context. Keep entire episodes/task families together in splits. Luna judgments are predictions, not ground truth.

- [Detailed runtime plan](docs/runtime-plan.md)
- [Fleet benchmark direction](docs/fleet-benchmark-direction.md)
- [Source research](docs/wide-benchmark-search.md)

Built for **Verifiable execution for distributed AI systems**: inspectable findings with explicit cost, evidence, and failure limits.
