# Cloud-Bean: Interactive Visual UI Specification

Updated: 2026-09-13.
Status: Technical design for the fleet interaction graph and dashboard.

## 1. Overview & Purpose

The Cloud-Bean visual interface provides an interactive, node-link visualization of multi-agent fleet operations. It is designed for operators to:
1. **Visually identify trends and clusters**: Rapidly see which agents are converging on shared resources, forming secret hubs, or engaging in edit wars.
2. **Inspect evidence**: Click on any agent node, resource node, or connection edge to view cited evidence, raw messages, and chronological timelines.
3. **Audit budget and findings**: Review Luna judge assessments, token spend, and active alerts in real time.

---

## 2. Graph Topology & Visual Encodings

```text
 ┌────────────────────────────────────────────────────────────────────────┐
 │                      Fleet Interaction Canvas                          │
 │                                                                        │
 │         (Agent-1)               (Agent-2)                              │
 │            │                       │                                   │
 │            │ [edits]               │ [overwrites]                      │
 │            ▼                       ▼                                   │
 │      ┌───────────┐           ┌───────────┐                             │
 │      │ Resource  │◄─────────►│ Resource  │◄─────── (Agent-3)           │
 │      │ (Wiki A)  │  [links]  │ (Wiki B)  │         [reads]         │
 │      └───────────┘           └───────────┘                             │
 │            ▲                                                           │
 │            │ [shared hash]                                             │
 │         (Agent-4)                                                      │
 └────────────────────────────────────────────────────────────────────────┘
```

### 2.1 Node Specifications

| Node Type | Shape | Color Coding | Label / Details |
| :--- | :--- | :--- | :--- |
| **Agent** | Circle (`●`) | • Green: Normal / Benign<br>• Yellow: Flagged in Candidate Group<br>• Red: Involved in Confirmed Finding (`concerning`)<br>• Gray: Insufficient Evidence / Inactive | Actor ID (`AgentRelent`), declared task role, event count |
| **Resource** | Rounded Rect (`■`) | • Blue: Low-traffic resource<br>• Orange: Emerging hub (high fan-in)<br>• Crimson: Conflict hot-spot (rapid overwrites) | Resource URI / Wiki Page name (`wiki:LinearAlgebra_Tricks`), revision count |
| **Finding / Alert** | Hexagon (`⬡`) | • Red: Concerning policy evasion / cheating<br>• Orange: Resource overload | Pattern label, severity, timestamp |

### 2.2 Edge Specifications

| Edge Type | Visual Style | Meaning |
| :--- | :--- | :--- |
| `WRITES` | Solid arrow (Agent → Resource) | Agent created or saved a revision to the resource. Thickness indicates edit count. |
| `READS` | Dashed arrow (Agent → Resource) | Agent accessed or queried the resource. |
| `CONFLICTS` | Red jagged line between Agents | Two agents engaged in rapid overwrites or revert battles (<120s). |
| `SHARED_ARTIFACT` | Purple dotted line between Agents | Two agents produced identical payload SHA-256 hashes across isolated tasks. |

---

## 3. UI Layout & Panes

```text
┌────────────────────────────────────────────────────────────────────────┐
│  CLOUD-BEAN FLEET DETECTOR                    [Spend: $0.428 / $10.00] │
├─────────────────────────────────────┬──────────────────────────────────┤
│                                     │ [Right Pane: Detail & Timeline]  │
│  [Main View: Interactive Graph]     │                                  │
│                                     │ Selected: AgentRelent            │
│  - Zoom, pan, drag nodes            │ Status: Concerning (Active Alert)│
│  - Filter: All / Hubs / Conflicts   │ Pattern: evaluation_cheating     │
│  - Time range slider (Scrubber)     │                                  │
│                                     │ Chronological Evidence:          │
│                                     │ 14:02:10 - Wrote revision 14     │
│                                     │   "Here is the token..."         │
│                                     │ 14:03:00 - Read by AgentMass...  │
│                                     │                                  │
│                                     │ Luna Assessment:                 │
│                                     │ "Deliberate cross-task leakage"  │
│                                     │ Tokens billed: 1,605 ($0.0010)   │
├─────────────────────────────────────┴──────────────────────────────────┤
│  [Bottom Pane: Active Findings Table & Metric Gauges]                  │
│  • Total Agents: 50  • Active Hubs: 3  • Conflicts: 7  • Spend: 4.3%  │
└────────────────────────────────────────────────────────────────────────┘
```

### 3.1 Key Interactive Features
1. **Interactive Force-Directed Layout**:
   - Built using modern web standards (React + SVG / Canvas or Cytoscape.js).
   - Nodes cluster naturally by shared resources; isolated tasks form distinct islands, while colluding groups form dense bridges.
2. **Timeline Scrubber**:
   - A timeline slider at the top allows operators to scrub through time from $T_0$ to $T_{now}$ and watch hubs emerge dynamically.
3. **Inspector Drawer**:
   - Clicking any agent or resource opens the right-hand inspection drawer showing full event history, snippets, cited evidence IDs, and Luna explanations.
4. **Budget & Coverage Meter**:
   - Live display of total spend against the hard cap, unflagged audit sample percentage, and deferred/skipped counts.

---

## 4. API Endpoints for UI

- `GET /api/v1/graph?start_time=...&end_time=...`
  - Returns `{ nodes: [...], edges: [...] }` formatted for graph rendering.
- `GET /api/v1/findings`
  - Returns list of active and historic findings with cited evidence IDs.
- `GET /api/v1/evidence/{packet_id}`
  - Returns full bounded evidence packet and Luna judgment.
- `GET /api/v1/budget`
  - Returns current spend, reservations, and audit stats.
- `POST /api/v1/replay`
  - Triggers offline deterministic replay and verifies identical finding generation.
