"""FastAPI REST application for Cloud-Bean monitoring and interactive UI backend."""

from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from cloud_bean.api.graph import build_interaction_graph
from cloud_bean.bench.trace_generator import trace_to_fleet_events
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

    # In-memory working buffer of recent events with thread lock
    recent_events_lock = threading.Lock()
    recent_events: List[FleetEvent] = []

    @app.get("/", response_class=FileResponse)
    @app.get("/dashboard", response_class=FileResponse)
    def index():
        static_file = Path(__file__).parent / "static" / "index.html"
        if not static_file.exists():
            return HTMLResponse("<h1>Cloud-Bean Observatory</h1><p>Static dashboard not found.</p>")
        return FileResponse(static_file)

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
        limit_agents: int = Query(default=50, ge=1, le=50),
        events_per_agent: int = Query(default=20, ge=2, le=100),
    ) -> Dict[str, Any]:
        """Load the pre-generated benchmark traces for up to 50 agents with ~85% normal work and 15% injected actions."""
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

        with recent_events_lock:
            recent_events.extend(all_fleet_events)

        # Process window through detection pipeline
        candidates, packets, findings = det_pipeline.process_window(
            events=all_fleet_events,
            window_start="2026-06-18T18:00:00Z",
            window_end="2026-06-18T22:00:00Z",
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

    return app
