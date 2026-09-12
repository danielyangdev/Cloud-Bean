# Benchmark research

Checked: 2026-09-12. Status: source audit and proposed benchmark design; no detector benchmark implemented or scored.

## Recommendation

Build **cloud-bean bench** from two separate suites:

1. **Existing agent runs:** adapt AgentDojo's recorded tool interactions for cheap offline detection tests.
2. **Controlled execution:** add small, stateful scenarios covering incident-like behavior and distributed failures. Export complete records for offline replay.

Use ASSEBench as a secondary breadth check. Keep system-security datasets such as OpTC optional. None of inspected sources alone supplies general agent events, task permissions, shared resource state, incident labels, and distributed delivery history.

Download and replay existing runs without fresh model calls. Controlled scenarios can use scripted actors. Distinguish recorded model behavior, scripted execution, and synthetic timing in every release.

## Existing sources

| Source | Available material | Fit and missing data |
| --- | --- | --- |
| [AgentDojo](https://github.com/ethz-spylab/agentdojo) | Public JSON run logs; tasks, tools, environment fixtures, and checks in repo. Four domains: banking, Slack, travel, workspace. MIT. | Best starting point for tool-level patterns. Prompt-injection focus; sampled messages lack action timestamps, host identity, network bytes, and shared fleet state. |
| [ASSEBench](https://github.com/Astarojth/AgentAuditor-ASSEBench) | Downloadable agent interactions with safety labels, risk types, and ambiguity markers. Repo declares Apache-2.0. | Broader safety coverage. Actions appear as text; parsing needs validation. Labels often depend on message meaning. Repo combines upstream sources; retain their provenance and terms. |
| [OpenClawBench](https://arxiv.org/html/2605.29253v1#Sx6.SS2) | Paper reports 31,264 annotated trajectories, event descriptors, anomaly spans, and quality tiers. | Promising process-anomaly source. Anonymous release returned HTTP 403 during checks; data contents unverified. Many labels concern reasoning or insufficient evidence, beyond metadata-only detection. |
| [HINTBench](https://arxiv.org/abs/2604.13954) | Paper reports 629 synthetic trajectories with risk and step labels. | Relevant to failures under benign instructions. Anonymous download returned HTTP 403; no verified corpus available in this audit. |
| [AgentHarm](https://huggingface.co/datasets/ai-safety-institute/AgentHarm) | Harmful and benign task definitions with benchmark tools. | Primarily tests response to harmful requests; dataset card is not a ready execution-event corpus. Authors request evaluation-only use. Do not use as proposed ML training pool. |
| [OpTC](https://github.com/FiveDirections/OpTC-data) | Endpoint and network records, schema, red-team ground truth, benign activity. Public-domain release. | Good optional test for file/process/network detection across hosts. About 1 TB compressed; 500 observed hosts. No AI task or agent identity. Download links inspected; bulk data not downloaded. |

### Verified files

Audit details, sample URLs, and SHA-256 hashes: [benchmark-source-audit.json](benchmark-source-audit.json).

- AgentDojo revision `089ed468cf3ed0322acc66b0211f26d9d90dbf60`: 36,679 JSON files under `runs/`, totaling 426,293,413 bytes. 35,875 paths are user-task runs; remaining files are not interchangeable with those runs. Counts are inventory, not validated usable examples.
- Inspected 24 AgentDojo logs across four domains and three pipeline directories. Samples contained 55 proposed tool calls, arguments, tool results, and run-level scores. No per-message timestamps. Pipeline directory count does not equal distinct model count.
- ASSEBench revision `fa5f99797073fd9a8d012268bc2b7dc27d05f4b1`: `ASSEBench/dataset/AgentJudge-strict.json` downloaded and parsed. 1,476 records; 835 labeled `1`, 641 labeled `0`. Strict/loose files overlap; do not concatenate them as independent examples.

Direct locations:

- [Pinned AgentDojo runs](https://github.com/ethz-spylab/agentdojo/tree/089ed468cf3ed0322acc66b0211f26d9d90dbf60/runs).
- [Pinned ASSEBench JSON](https://raw.githubusercontent.com/Astarojth/AgentAuditor-ASSEBench/fa5f99797073fd9a8d012268bc2b7dc27d05f4b1/ASSEBench/dataset/AgentJudge-strict.json).

### Label traps

AgentDojo's `security` is not a universal safe/unsafe label. For attacked runs, checks can return whether attacker goals succeeded. Clean runs set it to `true` without an attack check. Some execution-error paths also set it to `true`. Map labels using run type, error status, and matching benchmark version. An unsuccessful attack does not establish absence of every other concerning behavior. Sources: [task checks](https://github.com/ethz-spylab/agentdojo/blob/089ed468cf3ed0322acc66b0211f26d9d90dbf60/src/agentdojo/default_suites/v1/banking/injection_tasks.py), [runner](https://github.com/ethz-spylab/agentdojo/blob/089ed468cf3ed0322acc66b0211f26d9d90dbf60/src/agentdojo/benchmark.py).

Keep benchmark outcome labels separate from new cloud-bean incident labels. Never label every run containing an attack prompt as unsafe. Keep failed, incomplete, and ambiguous runs separate from confirmed negatives.

## Incident relevance

Reported patterns include scope escape, credential access, changing access routes, persistent retries, shared coordination, and concealment. Use these as scenario requirements, with harmless local services and dummy resources. Sources: [OpenAI account](https://openai.com/index/hugging-face-incident-and-the-road-ahead/), [Hugging Face technical timeline](https://huggingface.co/blog/agent-intrusion-technical-timeline), [Redwood investigation](https://www.redwoodresearch.org/research/hugging-face-incident).

No complete, labeled incident event corpus was found in inspected releases. Hugging Face's [interactive timeline files](https://huggingface.co/spaces/huggingface/anatomy-of-frontier-lab-model-intrusion/tree/main) expose presentation data in `index.html`, not a complete telemetry dump with normal controls. Use incident reports for scenario design, not as training examples representing full executions.

## Proposed scenario coverage

| Concerning pattern | Matched normal control |
| --- | --- |
| Repeated denied access followed by use of a different, unauthorized identity | Authorized credential rotation and successful retry |
| Sensitive resource read followed by transfer to an unapproved destination | Approved backup of same-sized data |
| Persistent retries through alternate destinations after denial | Bounded retries after transient service failure |
| Unexpected process or task fan-out exceeding task budget | Approved parallel work within same budget |
| Shared writes and reads across isolated tasks | Allowed collaboration or shared read-only dependencies |
| Agents jointly exceed transfer, request, or spending limits | Similar workload remaining within fleet budget |
| Attempt to remove logs or disable collection | Authorized log rotation; separately, ordinary sensor outage |
| Duplicate persistent effect after lost acknowledgment | Retry with same operation ID and one confirmed effect |

These are designed scenarios inspired by incident patterns, not claims that every pattern occurred in that incident. Implement stateful local file, identity, job, messaging, and transfer services. Actors use services; independent service receipts establish actual effects. Shared scenarios must use shared state. Interleaving independent traces alone cannot establish cooperation or causal links.

## Required data package

| File | Required contents | Consumer |
| --- | --- | --- |
| `manifest.json` | Schema version, source revisions, licenses, file hashes, generation seed, observed/scripted origin, supported sensor fields | Loader and evaluator |
| `tasks.jsonl` | Opaque task/agent/worker IDs, task family, structured permissions, resource scopes, budgets, allowed collaboration, policy changes | Detector |
| `resources.jsonl` | Resource IDs, types, owners, trust zones, sensitivity, version history where observed | Detector |
| `events.jsonl` | Stable event ID, worker boot ID and sequence, task/agent ID, call/operation ID, event type, tool/action, resource/destination, result, available measurements | Detector, streamed |
| `receipts.jsonl` | Independently recorded effect IDs and state transitions | Evaluator; detector sees only receipts its production sensors would expose |
| `labels.jsonl` | Incident family, affected entities, evidence IDs, first observable step, outcome, ambiguity, label source | Evaluator only |
| `delivery.jsonl` | Seeded delivery schedule: delays, duplicates, drops, reconnects, crashes, restarts | Replay harness only |
| `splits.json` | Train/validation/test groups by task template, source model, and scenario family | Training and evaluator |
| `reference/` | Original logs, fixtures, tool definitions, adapter mappings, and source licenses | Offline audit; excluded from normal detector input |

Core events should cover `tool.call` and `tool.result`. Optional sensor profiles add file, network, process, identity, and policy events. This keeps API-only agents usable while letting container agents supply richer evidence. Generic does not mean every agent exposes every field.

Preserve nulls for missing timestamps, byte counts, object versions, and permissions. Record whether each added value is observed, derived, or simulated. Do not divide total run duration into invented measured action timings. Serialized result size is not network traffic size. A tool call expresses intent; successful execution needs a result or independent receipt.

Tool adapters map explicit fields into common actions such as read, write, send, spawn, authenticate, and delete. Unknown tools stay unknown. Parse structured arguments without executing embedded code. Readable prompts may be retained for audit; metadata detectors need human-authored structured task policies, not an LLM translating prompts during replay. Count policy/adaptor setup effort in evaluation.

Historical AgentDojo runs support order-based detection first. Timing tests use marked synthetic schedules; syscall and real transfer tests require newly captured execution. Where original runtime versions or initial state cannot be recovered, retain logs for observation replay but do not claim exact environment re-execution.

## Evaluation rules

- Score incident recall, precision, false alerts per 1,000 clean runs, and delay from first observable evidence. Use steps when action timestamps are absent. Report alerts before confirmed harm separately.
- Report monitoring bytes/event, peak memory, CPU time, collector overhead, and retained evidence volume. Measure end-to-end costs, including local parsing, not only central ingestion.
- For each seed, compare uninterrupted replay with duplicate/delayed delivery and crash recovery. Under recoverable delivery, final alert IDs and findings should agree within declared lateness rules. With permanent loss, report coverage and any lost detections; do not promise equal findings.
- Run rules-only and small non-LLM models on identical allowed fields. Possible baselines: counts, action-transition probabilities, and tree models over rolling features.
- Split related tasks, attack variants, matched controls, and scenario seeds together. Hold out source models and scenario families separately. Random event splits leak near-identical runs into testing.
- Exclude attack names, risk explanations, source filenames, final grades, future events, and incident IDs from detector features. Fit normalization and thresholds on training/validation data only.
- Audit which labels are detectable from allowed metadata. Score observable policy violations separately from text-dependent judgments. Identical allowed inputs with different labels expose a detection limit, not a model-training problem.
- Use varied normal controls and low incident prevalence. High scores on scripted rules alone establish synthetic scenario coverage, not general rogue-agent detection.

## Build order

1. Adapt a pinned AgentDojo subset; retain source labels and add audited structured task policies.
2. Add controlled identity, transfer, retry, and budget scenarios with matched normal controls and receipts.
3. Add shared-state fleet scenarios, then delivery faults and recovery scoring.
4. Add ASSEBench's metadata-observable subset for breadth. Consider OpenClawBench/HINTBench only after downloads and field quality are verified.

First release should include frozen data, adapters, replay harness, labels, and baseline scores. Proposed files above are a release contract; they have not been generated by this research task.
