# Cloud-Bean: Planned Git History & Atomic PR Roadmap

Updated: 2026-09-13.
Status: Roadmap for incremental, test-driven PR execution.

## 1. Overview of PR Lifecycle

Each PR follows a strict lifecycle:
1. **Branch & Goal**: Scoped to an atomic milestone.
2. **TDD / Implementation**: Unit/integration tests written and verified passing.
3. **Subagent Review**: Reviewed by a dedicated `reviewer` subagent for conformance, code quality, and falsification before integration.
4. **Integration**: Clean commit with structured Conventional Commits message.

---

## 2. Planned PR Roadmap

| PR # | Branch | Title & Scope | Dependencies |
| :--- | :--- | :--- | :--- |
| **PR 1** | `feat/docs-and-specs` | **docs: concrete system architecture, data models, signals, and UI specs**<br>Establish baseline docs for execution. | None |
| **PR 2** | `feat/core-schemas` | **feat(core): data models and validation schemas for events, packets, judgments, findings**<br>Add Pydantic/dataclass models in `src/cloud_bean/schemas/` with tests in `tests/test_schemas.py`. | PR 1 |
| **PR 3** | `feat/wiki-ingestion` | **feat(ingest): Collusion Wiki SQLite loader and normalized event stream**<br>Add `src/cloud_bean/ingestion/collusion_wiki.py` to extract real board revisions, pages, and events. | PR 2 |
| **PR 4** | `feat/fleet-signals` | **feat(signals): rolling heuristic signal detectors for hubs, conflicts, and hashes**<br>Implement emerging hubs, conflicting writes, shared artifact hashes, and 10% audit sampler in `src/cloud_bean/signals/`. | PR 2, PR 3 |
| **PR 5** | `feat/evidence-selector`| **feat(evidence): bounded evidence packet builder with policy and context flags**<br>Implement token-bounded packet creation in `src/cloud_bean/evidence/`. | PR 4 |
| **PR 6** | `feat/luna-judge-budget`| **feat(judge): Luna client, structured Responses API parser, and budget ledger**<br>Implement transactional reservation, spend capping, and judgment validation in `src/cloud_bean/judge/`. | PR 5 |
| **PR 7** | `feat/engine-and-replay`| **feat(engine): findings generation, alert rules, and deterministic replay engine**<br>Implement accepted judgment ledger and offline replay verification. | PR 6 |
| **PR 8** | `feat/fastapi-backend` | **feat(api): FastAPI REST backend with graph, findings, and budget endpoints**<br>Serve graph data (`nodes`, `edges`) and timeline records for the visual UI. | PR 7 |
| **PR 9** | `feat/interactive-ui`  | **feat(ui): interactive web dashboard with agent-resource graph and trend inspector**<br>Build interactive UI canvas showing agents as nodes, shared resources, connections, and evidence inspector. | PR 8 |
| **PR 10**| `feat/trace-generation`| **feat(bench): 50-agent Collusion Wiki trace extraction and generation pipeline**<br>Extract top 50 active agents, generate OpenAI-formatted traces (80-90% normal work + 10-20% real board actions). | PR 3 |
| **PR 11**| `feat/e2e-and-polish`  | **test(e2e): failure injection, crash recovery verification, and final polish**<br>Comprehensive verification under worker crash, budget exhaustion, and duplicate deliveries. | PR 7-10 |

---

## 3. Review Agent Checklist per PR

Before any PR is merged, the `reviewer` subagent must check:
- [ ] Conformance: Does the code match the approved specification in `docs/`?
- [ ] Test coverage: Are unit tests included and passing?
- [ ] No regression: Do existing tests still pass?
- [ ] Code quality: Are type annotations, docstrings, error handling, and clean boundaries present?
- [ ] Scope discipline: Is there any unjustified scope creep?
