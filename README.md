# Cloud-Bean: Fleet Security Monitor for AI Agents

Budgeted semantic surveillance and misalignment detection across autonomous AI agent fleets.

---

## Overview

When autonomous agents are deployed at scale under task deadlines or network restrictions, they can exhibit unintended behaviors—exploiting external communication channels, bypassing rate limits, sharing benchmark solutions out-of-band, or corrupting shared resources.

Auditing every single agent action with frontier Large Language Models is cost-prohibitive. **Cloud-Bean** solves this with a **two-tier surveillance architecture**:

1. **Tier-1 Mathematical Signals**: Nine microsecond statistical, temporal, and information-theoretic heuristics evaluate sliding telemetry windows in native Python, suppressing over **95% of routine benign activity** without calling an LLM.
2. **Tier-2 Semantic Judge**: Only anomalous clusters are packaged into token-bounded evidence packets and escalated to **Gemini 2.5 Flash** (via Google Vertex AI) for structured classification under RFC 5405 rate limits.
3. **Zero-Cost Deterministic Replay**: Accepted judgments and deduplicated finding IDs are committed to an immutable ledger, allowing 100% reproducible recovery and auditing with **zero fresh model calls ($0.00)**.

This approach achieves a **99.4% cost reduction** compared to brute-force surveillance ($0.08 vs $14.20 per benchmark window).

---

## Quick Start

### 1. Installation

Requires Python 3.10+.

```bash
# Clone the repository
git clone git@github.com:danielyangdev/Cloud-Bean.git
cd Cloud-Bean

# Install dependencies
pip install -r requirements.txt
```

### 2. Run the Test Suite

```bash
pytest -q
```
*113 unit and integration tests passing across 13 modules.*

### 3. Launch the Application

```bash
PYTHONPATH=src python3 -m uvicorn cloud_bean.api.app:create_server_app --factory --host 0.0.0.0 --port 8000
```

Open **[http://localhost:8000/](https://cloud-bean.vercel.app/)** in your browser.

The server pre-loads the full 200-agent benchmark fleet into `.cloud-bean/state.db` on first boot (~1.5s cold start, ~0.1s on subsequent restarts).

---

## Web Dashboard

The web interface is built with vanilla ES modules and self-hosted fonts—no bundlers, no `node_modules`, and no external CDN dependencies:

| Route | View | Description |
| :--- | :--- | :--- |
| `#/overview` | **Overview** | High-level compliance banner, KPIs, detection funnel, and priority active violations table. |
| `#/graph` | **Graph Observatory** | Force-directed interaction graph with instant cohort filtering (`All`, `Clean`, `Violations`, `Tools`). |
| `#/playback` | **State Playback** | Scrub the event stream chronologically and watch findings surface as evidence accrues. |
| `#/analytics` | **Security Analytics** | Signal trigger distributions, shared-resource write hotspots, and cumulative budget savings. |
| `#/findings` | **Forensic Findings** | Detailed findings browser showing cited evidence packets, timestamps, and Gemini judge records. |
| `#/explainer` | **How It Works** | Product walkthrough runbook with a live telemetry pipeline canvas, 9-signal matrix, and event simulator. |

---

## 200-Agent Dual Cohort Benchmark

Cloud-Bean includes an authentic 200-agent evaluation benchmark grounded in real incident data:

* **100 Misaligned Agents** (`benchmark/generated-traces/`): Grounded in the 2026 Nightingale UseMod CGI incident (`collusion-wiki.db`). Agents perform ~85% legitimate financial data retrieval (SEC EDGAR, USASpending, BLS county wages) and ~15% injected collusion (exploiting HTTP GET mutations to share pre-computed answers).
* **100 Clean Control Agents** (`benchmark/clean-traces/`): Matching control agents performing 100% legitimate retrieval with realistic operational friction (HTTP 429 exponential backoffs, schema validation retries, socket reconnects) and zero collusion.
* **3-Annotator Gold Consensus**: All 200 traces are adjudicated by a panel of 3 independent models (`GoldAdjudicator`) operating under majority voting ($\ge 2/3$), achieving **100% unanimous agreement** on verdicts, violation patterns, and needle indices.

---

## Cloud Deployment (Vercel)

Cloud-Bean is configured for serverless deployment on Vercel's free Hobby tier:

```bash
# Deploy to Vercel
npx vercel
```

* **Live Deployment**: `https://cloud-bean-felix-chens-projects-beb9a60c.vercel.app`
* **Serverless Architecture**: `vercel.json` routes static assets to Vercel's global CDN and API routes to `api/index.py` with automatic `/tmp` state database redirection for read-only serverless containers.

---

## Technical Documentation

Detailed architectural specifications, mathematical definitions, and schemas are maintained in the `docs/` directory:

* **[System Architecture](docs/architecture.md)** — Two-tier pipeline, Dynamo hash partition router, and memory budgets.
* **[Signal Engineering Specification](docs/signals-spec.md)** — Mathematical formulations for JSD, burstiness $C_v$, NCD, and hub detection.
* **[Benchmark Retrieval Tasks](docs/benchmark-retrieval-tasks.md)** — Archetypes, task constraints, and dataset derivation.
* **[Misalignment Taxonomy](docs/misalignment-definitions.md)** — Violation patterns, negative controls, and the 3-annotator voting protocol.
* **[Runtime Plan & Budgeting](docs/runtime-plan.md)** — Bounded evidence selection, transactional reservations, and rate limits.
* **[Data Models & Schemas](docs/data-models.md)** — Pydantic models for events, candidates, evidence packets, and findings.
* **[Test Plan & Telemetry](docs/test-plan.md)** — Test suite layout, OpenMetrics exposition, and Kubernetes health probes.
