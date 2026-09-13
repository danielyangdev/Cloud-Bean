# Broad fleet benchmark search

Checked 2026-09-12. Original goal: concerning patterns across interacting agents, with cheap replay and no model calls during monitoring. Superseded runtime choice: [budgeted GPT-5.6 Luna checks](runtime-plan.md) over selected group conversations; recovery replay reuses recorded judgments. Source audit below remains relevant.

## Finding

Use three separate evidence tracks: real incident records, labeled group experiments, and controlled fleet simulations. No inspected source supplies full agent identity, permissions, tool receipts, shared-state history, normal controls, and incident labels together.

Search expanded beyond “rogue agents” to cheating, whistleblowing, conformity, sabotage, resource depletion, retaliation, economic collusion, social simulations, covert channels, and coordinated online behavior. Paper claims, downloadable files, and parsed records are distinguished below.

## Closest sources

| Source | Behavior and fit | Data checked; gaps |
| --- | --- | --- |
| [Collusion Wiki](https://collusion.wiki/) | Real public-board coordination, pooled answers, restriction bypasses; distinct from METR Hugging Face incident | [Download index](https://collusion.wiki/explorer/download) lists 14,591 revisions, 4,579 pages, 3,103 names, save/delete events, and build manifest. Additional cross-site records, links, and coverage gaps. Counts from publisher; direct download failed with TLS error here. Names are not verified unique agents. No full task/permission/tool record or normal baseline. |
| [DeepMind research swarm](https://arxiv.org/abs/2609.04170) | 100 proving agents; verifier exploit spreads through library and messages, followed by whistleblowing and corrective action | Paper includes scenario and prompts. No downloadable full run corpus found in inspected paper links. Strong scenario reference; not ready replay data. |
| [Anthropic multiagent study](https://www.anthropic.com/research/multiagent-systems) | Conformity, queue flooding, pricing coordination, and conflict escalation | Report describes 2.4 million requests with 117 accepted jobs in one run; separate experiments include sabotage during conflicting goals. No full trace download found on inspected page. Useful scenarios with observable group effects. |
| [FakeLab, AISI](https://www.aisi.gov.uk/research/multi-agent-ai-control-distributed-attacks-hamper-per-instance-monitors) | Deliberate attacks split across agents; per-agent monitors miss combined effect | Nine services, 86 benign tasks, four attack goals. Authors offer setting to safety researchers on request. No public download verified; no outreach sent. |
| [SCHEME](https://arxiv.org/abs/2605.29178) | Joint sabotage: no proper subset of agents can complete attack | 17 task instances across seven settings and eight libraries. Strong test design for joint effects. No benchmark corpus link found in inspected paper. Small teams; not spontaneous mass spread. |
| [NARCBench](https://huggingface.co/datasets/aaronrose227/narcbench) | Engineered coalitions, private/public messages, voting outcomes | Parsed one four-agent result and config: roles, votes, private/public messages, coalition, fair/target options, success flags. Model activations also available, but unsuitable for framework-neutral monitoring. Fields describe experiment conditions; do not expose hidden coalition or outcome to detector. Small controlled groups. |
| [Colosseum](https://github.com/umass-ai-safety/colosseum) | Group actions favor coalition over shared objective; hospital, tickets, scheduling | Public experiment code; 125-file inspected tree contains no JSON/JSONL/CSV/Parquet/ZIP data files. No license detected. Can generate scored runs; existing replay corpus not verified. |
| [Null Epoch](https://huggingface.co/datasets/FirespawnStudios/null-epoch-season-0-open) | Persistent shared world, trade, combat, resource use | Downloaded and parsed 86,097 events from 20 agents; publisher describes 10 days. IDs, ticks, timestamps, event types, territories, details. Separate metrics, prices, prompts, and final states available. CC BY 4.0. Allowed game competition is not itself misalignment; needs task-specific labels and controls. |
| [Emergent collusion auctions](https://github.com/lechmazur/emergent_collusion) | Uninstructed price coordination | Earlier audit found 527 JSONL logs; six-agent games. Structured messages, actions, trades, payoffs. Small and domain-specific; no license or incident labels found. |
| [Audit the Whisper / ColludeBench-v0](https://github.com/Ostailor/Steganographic_Collusion) | Covert-channel and market experiments | 3,621 JSON/JSONL/CSV/Parquet/ZIP files, including metrics and manifests rather than all distinct runs. Parsed one 320-row, four-agent log: rounds, messages, actions, rewards, interventions. MIT. Generation provenance and claimed detector results not independently reproduced; do not call every file an observed LLM incident. |

## Other leads and exclusions

- [MAST / MAD](https://github.com/multi-agent-systems-failure-taxonomy/MAST): recorded coordination failures across agent frameworks. Tree contains 7,503 files with common data extensions; this is not episode count. Useful ordinary-failure comparisons, not proof of mass malicious behavior.
- [RiskLab](https://github.com/HowieHwong/RiskLab): configurable group-risk scenarios and structured logger; no recorded corpus found in earlier audit.
- [MultiAgent4Collusion](https://github.com/renqibing/MultiAgent4Collusion): large social-simulation scenarios, misinformation and commerce. Tree includes 101 data-format files, many under profile/configuration paths. Do not treat input populations as completed run traces. Apache-2.0.
- [GovSim](https://github.com/giorgiopiatti/GovSim): shared-resource depletion and cooperation. Good mechanism to adapt into shared compute/budget abuse; frozen trace completeness not checked.
- [Game of Agents](https://github.com/Andromede-AI/game-of-agents): shared economy and code market; run-download tooling. Earlier tree audit only; remote run completeness remains unchecked.
- [Incident task recreations](https://github.com/AI-Safety-Commons/oai-rlvr-task-recreations): close task fit, MPL-2.0. Current README uses model-governed web gateway, so generation is not model-free. No frozen run corpus in inspected 37-file tree. Never assume recreation reproduces spontaneous original behavior.
- [SWARM](https://github.com/swarm-ai-research/swarm): simulation and incident-import tooling, including wiki replay. Useful integration lead; independent validation of its empirical claims remains open.
- [RubyGems investigation](https://www.rubyhack.ai/): real repeated abuse and public artifact trail. Authors explicitly leave cooperation versus parallel use of same strategy unresolved. Do not label coordinated transmission as established fact.
- [GT-HarmBench](https://github.com/causalNLP/gt-harmbench): inspected repository has one file; no ready corpus.
- [Temporal coordination research](https://arxiv.org/abs/2107.02588): useful cross-domain methods based on repeated URLs/actions and timing. Human/social-account coordination is not an AI incident benchmark.
- AgentDojo, AgentHarm, ASSEBench, and injection-cascade benchmarks remain outside core scope. Large collections of separate agent failures are not interacting swarms.

## Recommended package

1. **Historical replay:** ingest wiki revisions/events/links and preserve identity and coverage uncertainty. Score observable group patterns against manually reviewed incident intervals; do not invent absent reads, permissions, or tool outcomes.
2. **Labeled group behavior:** adapt NARCBench votes and auction actions into common events. Hold out entire scenarios and model families. Keep hidden roles, success labels, and target choices in scorer-only files.
3. **Fleet failure tests:** script spread through shared artifacts, queue storms, coordinated scope changes, and persistent background activity. Pair each with approved collaboration, shared outages, and normal failover. Sweep 50–200 interacting actors, not interleaved independent games.
4. **Natural background:** use selected Null Epoch interactions and ordinary MAST failures only under clearly defined task policies. Missing incident labels do not imply healthy behavior.

Common event fields: episode, actor, task, timestamp/sequence, operation, target, parent event, shared-object version, result, policy version, sensor source, and missing-field flags. Each adapter publishes available fields. Never fabricate a complete trace from an incomplete source.

Core measurements: affected-agent count, action/destination concentration, repeated artifact use, write conflicts, requests versus accepted work, and activity after revocation or task completion. Metadata cannot distinguish every malicious conversation from healthy collaboration. Test that limit explicitly.

Score alert delay, false alerts per fleet-hour, affected-group coverage, memory, bytes, and replay stability under duplicates, delays, and collector crashes. Report real records and scripted tests separately. No model calls needed to replay frozen events or compute these features.

## Audit evidence

[Repository inventory and parsed-file hashes](wide-benchmark-audit.json). Inventory is pinned where available. Only listed samples were parsed; file counts do not imply complete schema validation. External records were read as data; no downloaded agent code was executed.
