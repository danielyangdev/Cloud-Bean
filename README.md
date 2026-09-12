# cloud-bean

Cheap, fleet-wide detection of concerning AI agent behavior — no LLM calls, no full trace review, and alerts that survive crashes and replay identically.

cloud-bean watches execution metadata across workers, combines weak signals into useful alerts, and preserves evidence for review. Detection uses rules and small statistical models on cheap metadata, not routine LLM judgment on full transcripts.

**Status:** hackathon proposal. Runtime, detectors, and benchmarks are not built yet.

## Why now

Agent fleets are scaling faster than the tooling to watch them. Today's options are both bad:

- **No monitoring** — incidents (prompt injection, credential exfiltration, runaway spend, privilege creep) are caught after the fact, if at all.
- **Full-trace LLM review** — an LLM judge reads every transcript. Expensive at fleet scale, slow, non-deterministic, and itself a new attack surface (the judge can be fooled the same way the agent was).

cloud-bean is the cheap middle layer: metadata-only, rules + small local models, and — because nothing hosted or nondeterministic sits in the detection path — **replayable**. Rerun the same events through the same detector version and you get the same alerts, which is what lets a security team actually trust and audit a finding instead of re-litigating it.

**Who this is for:** teams running internal agent fleets, agent-platform providers who need to monitor tenant workloads, and AI infra teams that need an audit trail cheaper than "have an LLM read everything."

| | No monitoring | Full-trace LLM review | cloud-bean |
|---|---|---|---|
| Cost per action | $0, but $0 visibility | High (model call per trace) | Low (rules + local stats) |
| Latency | — | Seconds+ | Near real-time |
| Deterministic / replayable | N/A | No | Yes |
| Explainable evidence | No | Sometimes (model-dependent) | Yes (rule/model version + records) |
| Survives worker crash / partition | N/A | Unspecified | Yes, by design |

## What it watches

- **Boundary changes:** new destinations, sensitive resource access, unexpected child processes.
- **Behavior changes:** retry spikes, growing transfers, repeated access failures followed by privileged success.
- **Fleet patterns:** agents converging on unusual resources, repeating failures, or collectively exceeding budgets.

Alerts identify concerning activity for review. Unusual behavior alone does not prove harmful intent.

### Worked example

A code-review agent normally reads from one repo and posts to one Slack channel. Mid-task it:

1. Opens a connection to a new external host it has never contacted (**boundary change**).
2. Retries a failing auth call 40 times in a minute, then succeeds with elevated scope (**behavior change**: retry spike + privileged success after failures).
3. Two other agents in the fleet hit the same new host within the hour (**fleet pattern**: convergence).

Each signal alone might be noise. Combined, cloud-bean raises one alert referencing all three records, tagged with the detector rule versions that fired and the buffered evidence window, e.g.:

```json
{
  "alert_id": "a-7f3c...",
  "severity": "review",
  "triggered_by": ["boundary.new_destination", "behavior.retry_then_privileged", "fleet.convergence"],
  "agents": ["agent-114", "agent-201", "agent-330"],
  "evidence_window": ["evt-88210", "evt-88214", "..."],
  "detector_version": "rules-v0.3",
  "coverage": "complete"
}
```

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

## 72-hour scope

What we're actually building for the hackathon, versus the fuller vision above:

**In scope:**
- Local collectors emitting the metadata schema above from a handful of scripted agent workers.
- Durable event log with sequence-number dedup.
- A small rule set covering one detector per category (boundary / behavior / fleet).
- Alert generation with stable IDs and attached evidence records.
- Crash/replay demo: kill one worker, restore, replay, diff alerts against an uninterrupted run.

**Out of scope for the hackathon (roadmap only):**
- The sequence-model experiment (nice-to-have if time remains).
- Multi-tenant deployment, auth, or a production UI.
- Real integrations with actual cloud providers — demo runs on scripted/simulated workers.

## Distributed systems contract

Target property: replaying recorded events produces identical final alert IDs and findings under fixed detector versions, event ordering, and lateness rules.

- Checkpoint detector state; replay durable records after crashes.
- Deduplicate events by worker identity and sequence number; deduplicate alerts by stable ID.
- Mark coverage incomplete during partitions or missing event ranges.
- Reconcile late records within a declared retention window; version revised findings.
- Report buffer overflow and expired evidence instead of silently treating missing data as healthy activity.

Assumptions: sensors and durable storage remain trusted; records needed for recovery remain within retention; replay uses deterministic inference and processing. Events lost before durable recording are outside replay guarantee. Sensor bypass remains outside detection coverage.

## Non-goals

- Not a replacement for full-trace review when you actually need semantic understanding of *why* an agent did something — cloud-bean flags, it doesn't explain intent.
- Not a prevention/blocking system in v0 — it's detection and evidence, not an enforcement layer.
- Not trying to catch a sufficiently careful adversary who stays inside normal-looking metadata; sensor bypass and adversarial evasion are explicitly out of scope for this contract.

## Hackathon demo

Run many healthy agents alongside scripted concerning activity: permission probes, unusual access, and rising outbound traffic. Show linked evidence across workers.

Kill detector and disconnect one worker. Restore both, replay buffered records, and compare final alerts with uninterrupted execution using identical input events.

## Evaluation

- Detection accuracy and false alerts on held-out workflows.
- Detection delay, including late-event reconciliation.
- Monitoring bytes per action, memory use, and worker overhead.
- Recovery time and final alert agreement after crashes and partitions.
- Cost and accuracy compared with full event retention and rules-only detection.

Built for **Verifiable execution for distributed AI systems**: inspectable detection behavior under explicit failure assumptions.
