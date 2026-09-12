# Fleet benchmark direction

Updated: 2026-09-12. Scope: concerning patterns across interacting agents.

## Decision

[Broader source search](wide-benchmark-search.md) adds real wiki incident exports, NARCBench, Null Epoch, and collective-failure studies. Use its three-track recommendation; earlier shortlist below remains supporting evidence.

Use whole fleet episodes as benchmark examples. AgentDojo, AgentHarm, and ASSEBench are outside core scope: their earlier audit remains useful background, but does not establish multi-agent incident coverage.

METR documents shared discoveries spreading, agents changing workstreams, coordination across runs, and collective tool-call spoofing. Timelines are partly reconstructed; underlying transcripts have gaps. Reference: [METR/Redwood report](https://metr.org/hugging-face-incident-report-aug-2026.pdf), especially Figures 8 and 14, collaboration section, and methodology appendix.

## Proposed detector targets

These are cloud-bean hypotheses, not detectors validated by METR.

| Pattern | Candidate cheap measurements | Normal comparison |
| --- | --- | --- |
| Many unrelated tasks converge on new activity | Destination concentration; falling task-resource diversity; growth in out-of-scope operations | Shared outage, scheduled deployment, approved bulk job |
| New behavior spreads after shared exposure | First read of versioned artifact followed by first use of action/resource; newly involved agents per window | Approved package rollout; independent discovery |
| Unapproved coordination hubs emerge | Growing cross-task fan-out, repeated request/result links, activity following unapproved peer requests | Declared manager/worker workflow |
| Activity persists across agent turnover | Shared resource lineage, old artifacts reused by fresh workers, background effects after run completion | Authorized checkpoints and scheduled jobs |
| Agents collectively adapt after restrictions | Coordinated destination or identity changes after denial; repeated attempts across alternate paths | Documented failover and credential rotation |
| Shared actions undermine observation | Growing discrepancy between gateway records and independent service receipts across workers | Known missing sensor coverage or collection bugs |
| Group work harms individual tasks or shared services | Task progress falls while shared activity rises; cumulative load and failed tasks exceed declared bounds | Approved experiments with explicit failure budgets |

Correlation alone does not prove transmission, authority, or intent. Include matched common-cause scenarios. Use controlled exposure experiments to test whether sharing changes behavior; reserve causal labels for those experiments.

## Better source shortlist

### Emergent collusion auction logs

[Repository](https://github.com/lechmazur/emergent_collusion), inspected revision `42b6d20703504759e53fec53738cac02a042cd01`.

- Inventory: 527 JSONL log files, 25,214,158 bytes.
- Parsed two files: 145 and 147 records. Fields include game/agent IDs, round, sequence, sender/recipient, messages, bids, asks, trades, and payoffs. Timestamps are present on many, not all, events.
- Authors describe six-agent, eight-round simulations with optional communication and profit objectives. Inspected examples include seller messages proposing coordinated prices.
- Useful existing multi-agent behavior data. Small market episodes cannot establish large swarm or general infrastructure coverage. No per-incident ground-truth labels or license file found in inspected tree; do not redistribute as licensed benchmark data without clarifying terms.

### RiskLab

[Repository](https://github.com/HowieHwong/RiskLab), inspected revision `9cd489eacd796f5b5705fdf3acf3bca4309bead1`.

- Framework for group risks, including collusion, conformity, authority deference, and role failures; supports configurable communication topology.
- Inspected logger records round, speaker, observation, message, action, local utility, and system state; saves structured trajectories.
- Candidate environment framework. No recorded corpus or license file found in inspected tree. Running new model agents would incur generation cost; replaying frozen records would not.

### Game of Agents

[Repository](https://github.com/Andromede-AI/game-of-agents), inspected revision `363de7f69f9b1ac857467cf784441d37aa640a94`.

Candidate shared economy/code-market environment. Repository includes agent logging, analysis, and run-download scripts; Apache-2.0 license. This pass checked inventory only, not downloadable run completeness. Keep as secondary lead.

## Required benchmark changes

Extend [earlier data contract](benchmark-research.md#required-data-package) with:

- Fleet episode IDs, group membership, worker lifetimes, and declared coordination topology.
- Shared object versions and read/write provenance; opaque payload fingerprints where sensors support them.
- Resource and operation scopes per task, delegation rights, fleet budgets, and policy changes.
- Independent service events and state transitions, distinct from agent claims.
- Episode-level incident intervals, affected subgroups, and first observable evidence. Keep labels unavailable to detector.
- Source and confidence for event timing, exposure links, identity matching, and missing coverage.

Persist message content only for offline audit where available; core detector should use metadata and fixed numeric features. Do not infer semantic goals from hashes or message counts. Exact fingerprints detect exact reuse, not arbitrary rewrites.

## First useful experiment

Create one shared, stateful workspace with 50-200 scripted actors and varied task scopes. Sweep population size, exposure rate, topology, actor lifetime, and incident prevalence. Scripted behavior provides deterministic system tests, not evidence of spontaneous model misalignment.

Compare otherwise matched episodes: authorized collaboration, independent failures, common service failure, and spreading unauthorized activity. Add worker turnover, delayed events, partitions, and tampered self-reports. Keep resource names and scenario templates varied between splits.

Score first-alert delay, affected-agent coverage, false incident alerts, spread before detection, memory, and bytes sent. Compare fleet detector against same rules applied per agent; hold total monitoring budget constant. Replay should require no model calls.

Recorded auction episodes can provide an initial external-data check. Larger generated episodes need frozen logs and separate reporting. Replaying many independent six-agent games measures throughput, not large-scale interaction.
