"""FastAPI REST application for Cloud-Bean monitoring and interactive UI backend."""

from collections import deque
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from cloud_bean.api.graph import build_interaction_graph
from cloud_bean.bench.trace_generator import (
    interleave_event_timestamps,
    trace_to_fleet_events,
)
from cloud_bean.engine.failures import FailureInjector, OfflineCollectorQueue
from cloud_bean.engine.pipeline import DetectionPipeline
from cloud_bean.engine.replay import ReplayEngine
from cloud_bean.engine.storage import JudgmentFindingStore
from cloud_bean.evidence.selector import EvidenceSelector
from cloud_bean.judge.budget import BudgetManager
from cloud_bean.judge.client import LunaJudgeClient
from cloud_bean.schemas.events import FleetEvent
from cloud_bean.schemas.finding import Finding
from cloud_bean.schemas.judgment import LunaJudgment
from cloud_bean.signals.detector import FleetSignalEngine


class IngestRequest(BaseModel):
    events: List[FleetEvent]
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    enable_audit: bool = True


class ReplayRequest(BaseModel):
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    enable_audit: bool = True


class FailureInjectRequest(BaseModel):
    mode: str
    rate: float = 0.3
    seed: int = 42


def _frontend_dir() -> Path:
    """Locate the frontend directory from cwd or relative to this module."""
    local = Path("frontend")
    if local.is_dir():
        return local
    return Path(__file__).resolve().parents[3] / "frontend"


def create_app(
    pipeline: Optional[DetectionPipeline] = None,
    store: Optional[JudgmentFindingStore] = None,
    budget_manager: Optional[BudgetManager] = None,
) -> FastAPI:
    """Create and configure the FastAPI application instance."""
    app = FastAPI(
        title="Cloud-Bean API",
        version="0.1.0",
        description="Budgeted detection of concerning behavior across AI agent fleets",
    )

    db_store = store or JudgmentFindingStore(":memory:")
    b_manager = budget_manager or BudgetManager(max_budget_usd=10.00)
    judge_client = LunaJudgeClient(budget_manager=b_manager, mock_mode=True)
    signal_engine = FleetSignalEngine()
    selector = EvidenceSelector()

    det_pipeline = pipeline or DetectionPipeline(
        signal_engine=signal_engine,
        evidence_selector=selector,
        judge_client=judge_client,
        store=db_store,
    )

    # In-memory working buffer of recent events with thread lock and bounded deque
    recent_events_lock = threading.Lock()
    recent_events: deque[FleetEvent] = deque(maxlen=10000)

    @app.get("/", response_class=FileResponse)
    @app.get("/dashboard", response_class=FileResponse)
    def index():
        frontend_file = _frontend_dir() / "index.html"
        if not frontend_file.exists():
            return HTMLResponse("<h1>Cloud-Bean</h1><p>Frontend index.html not found.</p>")
        return FileResponse(frontend_file)

    @app.get("/api/v1/health")
    def health() -> Dict[str, str]:
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/api/v1/graph")
    def get_graph(
        start_time: Optional[str] = Query(default=None, description="Window start ISO timestamp"),
        end_time: Optional[str] = Query(default=None, description="Window end ISO timestamp"),
    ) -> Dict[str, Any]:
        candidates = db_store.list_candidate_groups()
        findings = db_store.list_findings()

        with recent_events_lock:
            filtered_events = list(recent_events)

        if start_time:
            filtered_events = [e for e in filtered_events if e.timestamp >= start_time]
        if end_time:
            filtered_events = [e for e in filtered_events if e.timestamp <= end_time]

        return build_interaction_graph(
            events=filtered_events,
            candidates=candidates,
            findings=findings,
        )

    @app.get("/api/v1/findings", response_model=List[Finding])
    def get_findings() -> List[Finding]:
        return db_store.list_findings()

    @app.get("/api/v1/candidate-groups")
    def get_candidate_groups():
        return db_store.list_candidate_groups()

    @app.get("/api/v1/evidence/{packet_id}")
    def get_evidence_packet(packet_id: str):
        packets = db_store.list_evidence_packets()
        for p in packets:
            if p.packet_id == packet_id:
                return p
        raise HTTPException(status_code=404, detail="Evidence packet not found")

    @app.get("/api/v1/budget")
    def get_budget():
        return b_manager.get_ledger()

    @app.get("/api/v1/events")
    def get_events(
        limit: int = Query(default=20000, ge=1, le=50000),
        offset: int = Query(default=0, ge=0),
        actor_id: Optional[str] = Query(default=None),
        event_type: Optional[str] = Query(default=None),
    ) -> Dict[str, Any]:
        """Raw event stream, ordered so a client can treat list index as an ordinal cursor."""
        with recent_events_lock:
            events = list(recent_events)

        if actor_id:
            events = [e for e in events if e.actor_id == actor_id]
        if event_type:
            events = [e for e in events if e.event_type.value == event_type]

        events.sort(key=lambda e: (e.timestamp, e.event_id))
        page = events[offset : offset + limit]
        return {
            "total": len(events),
            "offset": offset,
            "count": len(page),
            "events": page,
        }

    @app.get("/api/v1/judgments", response_model=List[LunaJudgment])
    def get_judgments() -> List[LunaJudgment]:
        return db_store.list_accepted_judgments()

    @app.get("/api/v1/evidence")
    def list_evidence():
        return db_store.list_evidence_packets()

    @app.get("/api/v1/metrics/summary")
    def metrics_summary() -> Dict[str, Any]:
        """Aggregate counts backing the overview KPI tiles and analytics charts."""
        with recent_events_lock:
            events = list(recent_events)
        candidates = db_store.list_candidate_groups()
        findings = db_store.list_findings()
        packets = db_store.list_evidence_packets()

        actors = {e.actor_id for e in events}
        resources = {e.target for e in events if e.target}

        findings_by_pattern: Dict[str, int] = {}
        for f in findings:
            findings_by_pattern[f.pattern] = findings_by_pattern.get(f.pattern, 0) + 1

        candidates_by_signal: Dict[str, int] = {}
        for c in candidates:
            candidates_by_signal[c.trigger_signal] = (
                candidates_by_signal.get(c.trigger_signal, 0) + 1
            )

        covered: set = set()
        for p in packets:
            for ev in p.chronological_events:
                covered.add(ev.event_id)

        timestamps = [e.timestamp for e in events]
        return {
            "total_events": len(events),
            "total_agents": len(actors),
            "total_resources": len(resources),
            "candidates": len(candidates),
            "evidence_packets": len(packets),
            "judgments": len(db_store.list_accepted_judgments()),
            "findings": len(findings),
            "findings_by_pattern": findings_by_pattern,
            "candidates_by_signal": candidates_by_signal,
            "events_covered_by_evidence": len(covered),
            "coverage_ratio": (len(covered) / len(events)) if events else 0.0,
            "window": {
                "start": min(timestamps) if timestamps else None,
                "end": max(timestamps) if timestamps else None,
            },
        }

    @app.post("/api/v1/ingest/events")
    def ingest_events(req: IngestRequest) -> Dict[str, Any]:
        with recent_events_lock:
            recent_events.extend(req.events)

        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        w_start = req.window_start or (
            req.events[0].timestamp if req.events else now_iso
        )
        w_end = req.window_end or (
            req.events[-1].timestamp if req.events else now_iso
        )

        candidates, packets, findings = det_pipeline.process_window(
            events=req.events,
            window_start=w_start,
            window_end=w_end,
            enable_audit=req.enable_audit,
        )

        return {
            "ingested_count": len(req.events),
            "candidates_flagged": len(candidates),
            "packets_created": len(packets),
            "findings_generated": len(findings),
        }

    @app.post("/api/v1/load-benchmark-fleet")
    def load_benchmark_fleet(
        limit_agents: int = Query(default=100, ge=1, le=100),
        events_per_agent: int = Query(default=20, ge=2, le=100),
        retime: bool = Query(
            default=True,
            description="Spread synthetic tool-call timestamps across each agent's real activity span",
        ),
    ) -> Dict[str, Any]:
        """Load the pre-generated benchmark traces for up to 100 agents with ~85% normal work and 15% injected actions."""
        traces_dir = Path("benchmark/generated-traces")
        manifest_file = traces_dir / "manifest.json"
        if not manifest_file.exists():
            raise HTTPException(status_code=404, detail="Benchmark traces not found")

        manifest = json.loads(manifest_file.read_text())
        agent_entries = manifest.get("agents", [])[:limit_agents]

        all_fleet_events: List[FleetEvent] = []
        agent_summaries: List[Dict[str, Any]] = []

        for entry in agent_entries:
            trace_path = traces_dir / entry["file"]
            if trace_path.exists():
                trace_data = json.loads(trace_path.read_text())
                events = trace_to_fleet_events(trace_data)[:events_per_agent]
                all_fleet_events.extend(events)
                agent_summaries.append({
                    "agent_id": entry["agent_id"],
                    "normal_work_percentage": entry["normal_work_percentage"],
                    "loaded_events": len(events),
                })

        if retime:
            all_fleet_events = interleave_event_timestamps(all_fleet_events)

        with recent_events_lock:
            recent_events.extend(all_fleet_events)

        # Process window through detection pipeline with dynamic timestamps
        if all_fleet_events:
            w_start = min(e.timestamp for e in all_fleet_events)
            w_end = max(e.timestamp for e in all_fleet_events)
        else:
            now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            w_start, w_end = now_iso, now_iso

        candidates, packets, findings = det_pipeline.process_window(
            events=all_fleet_events,
            window_start=w_start,
            window_end=w_end,
            enable_audit=True,
        )

        return {
            "status": "loaded",
            "total_agents": len(agent_summaries),
            "total_events": len(all_fleet_events),
            "candidates_flagged": len(candidates),
            "findings_generated": len(findings),
            "agent_summaries": agent_summaries,
        }

    @app.post("/api/v1/failures/inject")
    def inject_failure(req: FailureInjectRequest) -> Dict[str, Any]:
        """Replay the current event window through an injected fault and report what changed.

        Exercises the same resilience paths covered by tests/test_failure_injection.py:
        findings are keyed by stable IDs, so duplicate or reordered delivery must not
        change the final finding set.
        """
        mode = req.mode
        valid = {"duplicates", "reordering", "collector_outage", "budget_exhaustion"}
        if mode not in valid:
            raise HTTPException(
                status_code=400, detail=f"mode must be one of {sorted(valid)}"
            )

        with recent_events_lock:
            base_events = list(recent_events)
        if not base_events:
            raise HTTPException(
                status_code=409, detail="No events loaded. Load the benchmark fleet first."
            )

        findings_before = len(db_store.list_findings())
        events_before = len(base_events)
        note = ""
        buffered = 0

        delivered_count = events_before
        suppressed = 0

        if mode == "duplicates":
            delivered = FailureInjector.inject_duplicates(
                base_events, duplicate_rate=req.rate, seed=req.seed
            )
            delivered_count = len(delivered)
            # At-least-once delivery is handled where a real collector handles it:
            # drop repeats by event_id before they reach the detectors, so the
            # processed stream is byte-identical to the clean one.
            seen: set = set()
            mutated = []
            for ev in delivered:
                if ev.event_id in seen:
                    suppressed += 1
                    continue
                seen.add(ev.event_id)
                mutated.append(ev)
            note = (
                f"Broker redelivered {delivered_count - events_before} events at-least-once; "
                f"{suppressed} suppressed by event-ID dedup before detection."
            )
        elif mode == "reordering":
            mutated = FailureInjector.inject_reordering(base_events, seed=req.seed)
            note = (
                "Delivery order jittered by network latency. Detectors window on event "
                "timestamps, not arrival order."
            )
        elif mode == "collector_outage":
            queue = OfflineCollectorQueue()
            queue.disconnect()
            delivered: List[FleetEvent] = []
            cutoff = max(1, int(len(base_events) * (1.0 - req.rate)))
            for idx, ev in enumerate(base_events):
                if idx == cutoff:
                    queue.reconnect()
                    delivered.extend(queue.flush_buffer())
                out = queue.emit(ev)
                if out is not None:
                    delivered.append(out)
            queue.reconnect()
            delivered.extend(queue.flush_buffer())
            buffered = queue.total_buffered
            mutated = delivered
            note = (
                f"Collector lost the broker and buffered {buffered} events to its local disk "
                f"queue, then flushed {queue.total_flushed} on reconnect. Nothing was dropped."
            )
        else:  # budget_exhaustion
            mutated = base_events
            note = (
                "Judge budget exhausted: further checks are recorded as skipped rather than "
                "silently treated as healthy."
            )

        if mode == "budget_exhaustion":
            ledger_before = b_manager.get_ledger()
            exhausted_before = ledger_before.checks_budget_exhausted
            # Leave no headroom, so every further reservation is refused.
            previous_cap = b_manager.set_max_budget(ledger_before.spent_usd)
            try:
                w_start = min(e.timestamp for e in mutated)
                w_end = max(e.timestamp for e in mutated)
                det_pipeline.process_window(
                    events=mutated, window_start=w_start, window_end=w_end, enable_audit=True
                )
            finally:
                b_manager.set_max_budget(previous_cap)
            ledger_after = b_manager.get_ledger()
            return {
                "mode": mode,
                "events_before": events_before,
                "events_after": len(mutated),
                "events_delivered": delivered_count,
                "findings_before": findings_before,
                "findings_after": len(db_store.list_findings()),
                "dedup_suppressed": 0,
                "checks_budget_exhausted": ledger_after.checks_budget_exhausted
                - exhausted_before,
                "note": note,
            }

        w_start = min(e.timestamp for e in mutated)
        w_end = max(e.timestamp for e in mutated)
        det_pipeline.process_window(
            events=mutated, window_start=w_start, window_end=w_end, enable_audit=True
        )
        findings_after = len(db_store.list_findings())

        findings = db_store.list_findings()
        finding_ids = [f.finding_id for f in findings]

        return {
            "mode": mode,
            "events_before": events_before,
            "events_delivered": delivered_count,
            "events_after": len(mutated),
            "events_buffered": buffered,
            "findings_before": findings_before,
            "findings_after": findings_after,
            "dedup_suppressed": suppressed,
            "findings_stable": findings_after == findings_before,
            "finding_ids_unique": len(finding_ids) == len(set(finding_ids)),
            "note": note,
        }

    @app.post("/api/v1/reset")
    def reset_state() -> Dict[str, Any]:
        """Clear the working event buffer so a demo can start from a cold dashboard."""
        with recent_events_lock:
            cleared = len(recent_events)
            recent_events.clear()
        return {"status": "reset", "events_cleared": cleared}

    @app.post("/api/v1/replay")
    def replay(req: ReplayRequest) -> Dict[str, Any]:
        replay_engine = ReplayEngine(
            store=db_store,
            signal_engine=signal_engine,
            evidence_selector=selector,
            judge_client=judge_client,
        )
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        w_start = req.window_start or now_iso
        w_end = req.window_end or now_iso

        with recent_events_lock:
            events_to_replay = list(recent_events)

        replayed_findings, missing_keys = replay_engine.replay_window(
            events=events_to_replay,
            window_start=w_start,
            window_end=w_end,
            enable_audit=req.enable_audit,
        )

        return {
            "replayed_findings_count": len(replayed_findings),
            "missing_judgment_keys_count": len(missing_keys),
            "llm_calls_made": replay_engine.llm_calls_made,
            "replayed_findings": replayed_findings,
        }

    # Mounted last so it never shadows an API route.
    frontend_dir = _frontend_dir()
    if frontend_dir.is_dir():
        app.mount(
            "/static", StaticFiles(directory=str(frontend_dir)), name="static"
        )

    return app
