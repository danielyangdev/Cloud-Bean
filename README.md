# cloud-bean

Cheap, fleet-wide detection of concerning AI agent behavior.

cloud-bean watches execution metadata across workers, combines weak signals into useful alerts, and preserves evidence for review. Detection uses rules and small statistical models—no LLM calls or routine analysis of full model traces.

**Status:** hackathon proposal. Runtime, detectors, and benchmarks are not built yet.

## What it watches

- **Boundary changes:** new destinations, sensitive resource access, unexpected child processes.
- **Behavior changes:** retry spikes, growing transfers, repeated access failures followed by privileged success.
- **Fleet patterns:** agents converging on unusual resources, repeating failures, or collectively exceeding budgets.

Alerts identify concerning activity for review. Unusual behavior alone does not prove harmful intent.

## Planned design

```text
Agent workers → Local collectors → Durable event stream → Detectors → Alerts
                       ↓                                    ↓
                 Recent event buffers                 Evidence timeline
```

1. Collect small records outside agent control: worker sequence number, agent and task IDs, action, resource, result, time, and byte count. Track object versions where available.
2. Summarize repeated activity locally. Batch records and keep recent detail in bounded buffers.
3. Combine signals across workers using rolling counts, resource relationships, and task-specific rules.
4. Preserve relevant buffered events when alerts fire. Include rule or model version, supporting records, and coverage gaps.

Optional ML experiment: train a small sequence model on normal execution metadata. Score unexpected action sequences and compare against rules-only detection on held-out runs. Run inference locally; no hosted model calls.

## Distributed systems contract

Target property: replaying recorded events produces identical final alert IDs and findings under fixed detector versions, event ordering, and lateness rules.

- Checkpoint detector state; replay durable records after crashes.
- Deduplicate events by worker identity and sequence number; deduplicate alerts by stable ID.
- Mark coverage incomplete during partitions or missing event ranges.
- Reconcile late records within a declared retention window; version revised findings.
- Report buffer overflow and expired evidence instead of silently treating missing data as healthy activity.

Assumptions: sensors and durable storage remain trusted; records needed for recovery remain within retention; replay uses deterministic inference and processing. Events lost before durable recording are outside replay guarantee. Sensor bypass remains outside detection coverage.

## Hackathon demo

Run many healthy agents alongside scripted concerning activity: permission probes, unusual access, and rising outbound traffic. Show linked evidence across workers.

Kill detector and disconnect one worker. Restore both, replay buffered records, and compare final alerts with uninterrupted execution using identical input events.

## Evaluation

See [benchmark research and proposed data contract](docs/benchmark-research.md) for inspected datasets, gaps, and build order.

- Detection accuracy and false alerts on held-out workflows.
- Detection delay, including late-event reconciliation.
- Monitoring bytes per action, memory use, and worker overhead.
- Recovery time and final alert agreement after crashes and partitions.
- Cost and accuracy compared with full event retention and rules-only detection.

Built for **Verifiable execution for distributed AI systems**: inspectable detection behavior under explicit failure assumptions.
