# cloud-bean

Cheap, fleet-wide detection of concerning AI agent behavior — no routine LLM calls, no full trace review, and alerts that survive crashes and replay identically.

cloud-bean watches execution metadata across workers, combines weak signals into useful alerts, and preserves evidence for review. Detection is rules and small statistical models running on every action; an LLM is used only to enrich the small number of already-flagged alerts, never as the thing deciding whether to alert.

**Status:** hackathon proposal. Runtime, detectors, and benchmarks are not built yet.

## Why now

Agent fleets are scaling faster than the tooling to watch them. Today's options are both bad:

- **No monitoring** — incidents (prompt injection, credential exfiltration, runaway spend, privilege creep) are caught after the fact, if at all.
- **Full-trace LLM review** — an LLM judge reads every transcript. Expensive at fleet scale, slow, non-deterministic, and itself a new attack surface (the judge can be fooled the same way the agent was).

cloud-bean is the cheap middle layer: metadata-only, rules + small local models, and — because nothing hosted or nondeterministic sits in the detection path — **replayable**. Rerun the same events through the same detector version and you get the same alerts, which is what lets a security team actually trust and audit a finding instead of re-litigating it.

**Who this is for:** teams running internal agent fleets, agent-platform providers who need to monitor tenant workloads, and AI infra teams that need an audit trail cheaper than "have an LLM read everything."

| | No monitoring | Full-trace LLM review | cloud-bean |
|---|---|---|---|
| Cost per action | $0, but $0 visibility | High (model call per trace) | Low (rules + local stats; LLM only on flagged alerts) |
| Latency | — | Seconds+ | Near real-time detection; LLM triage async, off the hot path |
| Deterministic / replayable | N/A | No | Yes, for the alerting decision |
| Explainable evidence | No | Sometimes (model-dependent) | Yes (rule/model version + records + optional LLM annotation) |
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

## Detection mechanics

Two tiers. Tier 1 runs on every action and decides whether to alert. Tier 2 runs only on what Tier 1 already flagged and adds context — it never gates the alert itself, so replay of the alerting decision stays exact.

**Tier 1 — rules + rolling stats (always-on, deterministic)**

| Category | Signal | How it's computed |
|---|---|---|
| Boundary | New destination / resource | Per-agent-role seen-set (Bloom filter); first-time access flags |
| Boundary | Sensitive resource access | Static tag list; any untagged-agent access flags immediately |
| Boundary | Unexpected child process | Per-task-type process allowlist |
| Behavior | Retry spike | EWMA of failure rate per (agent, resource, action); flag past mean + k·stdev |
| Behavior | Growing transfer | byte_count vs. historical p99 for that (agent, resource) pair |
| Behavior | Failure-then-privileged-success | Small state machine per (agent, resource): N failures then a higher-scope success |
| Fleet | Convergence | Distinct-agent count on a resource in a rolling window vs. baseline |
| Fleet | Fleet-wide failure spike | Same EWMA/z-score technique, keyed by resource across all agents |
| Fleet | Budget overrun | Running cost/byte sum per team vs. configured cap |

All Tier 1 state is small per-key counters/EWMAs, checkpointed periodically. Thresholds and logic are versioned config, not runtime-computed, so same version + same event order = same alert, always.

**Tier 1.5 — local text classifier (always-on, still no hosted calls)**

A small local model (not a hosted LLM) scores short text fields the agent produces — commit messages, chat messages, tool-call arguments — for sentiment/toxicity/urgency. Deterministic inference (fixed weights, no sampling), so it's just one more weak signal into the same combination logic as the stats above, not a separate judgment path.

**Tier 2 — LLM triage (triggered only, the expensive part gated by design)**

When Tier 1 fires, the alert and its evidence window are handed to an LLM for a one-time read: summarize what happened, explain why it's plausible or likely benign, suggest next steps. Cost scales with alert volume, not action volume — this is what keeps "LLM as judge" affordable. The LLM's output is attached to the alert as an annotation with its own version tag; it never changes the alert ID, severity, or whether the alert fired, so the deterministic replay guarantee below applies to detection regardless of what the LLM says.

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

Optional ML experiment: train a small sequence model on normal execution metadata. Score unexpected action sequences and compare against rules-only detection on held-out runs. Run inference locally; no hosted model calls. (See Detection mechanics above for the local text classifier and triggered LLM triage tiers.)

## 72-hour scope

What we're actually building for the hackathon, versus the fuller vision above:

**In scope:**
- Local collectors emitting the metadata schema above from a handful of scripted agent workers.
- Durable event log with sequence-number dedup.
- A small rule set covering one Tier 1 detector per category (boundary / behavior / fleet).
- Alert generation with stable IDs and attached evidence records.
- Crash/replay demo: kill one worker, restore, replay, diff alerts against an uninterrupted run.
- Tier 2 LLM triage on flagged alerts (single prompt, evidence window in, summary annotation out) — the part most likely to demo well live.

**Out of scope for the hackathon (roadmap only):**
- The local text classifier (Tier 1.5) and the sequence-model experiment — nice-to-have if time remains.
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

See [fleet benchmark direction](docs/fleet-benchmark-direction.md) for current scope and candidate sources. [Earlier source audit and data contract](docs/benchmark-research.md) covers supporting datasets and required fields.

- Detection accuracy and false alerts on held-out workflows.
- Detection delay, including late-event reconciliation.
- Monitoring bytes per action, memory use, and worker overhead.
- Recovery time and final alert agreement after crashes and partitions.
- Cost and accuracy compared with full event retention and rules-only detection.

Built for **Verifiable execution for distributed AI systems**: inspectable detection behavior under explicit failure assumptions.
