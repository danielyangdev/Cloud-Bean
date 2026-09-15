"""Tests for FastAPI backend and Graph API endpoints."""

from datetime import datetime, timezone
from fastapi.testclient import TestClient
import pytest

from cloud_bean.api.app import create_app
from cloud_bean.schemas.events import EventType, FleetEvent


def make_iso(base: datetime, offset_seconds: float) -> str:
    from datetime import timedelta
    dt = base + timedelta(seconds=offset_seconds)
    return dt.isoformat().replace("+00:00", "Z")


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_health_endpoint(client):
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "version": "0.1.0"}


def test_dashboard_index_endpoint(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "Cloud-Bean" in res.text
    assert "Fleet Security Monitor" in res.text
    assert "#/explainer" in res.text


def test_dashboard_explainer_assets(client):
    res = client.get("/static/js/pages/explainer.js")
    assert res.status_code == 200
    assert "How Cloud-Bean Works" in res.text


def test_budget_endpoint(client):
    res = client.get("/api/v1/budget")
    assert res.status_code == 200
    data = res.json()
    assert "max_budget_usd" in data
    assert "spent_usd" in data
    assert "reserved_usd" in data
    assert data["max_budget_usd"] == 10.00


def test_ingest_graph_and_findings_flow(client):
    base_time = datetime(2026, 9, 12, 14, 0, 0, tzinfo=timezone.utc)

    # 4 alternating rapid edits to trigger conflict and cheating detection
    events = [
        {
            "event_id": "evt_api_01",
            "timestamp": make_iso(base_time, 0),
            "actor_id": "AgentRelent",
            "task_id": "task_math_eval_1",
            "event_type": "resource_write",
            "target": "wiki:BypassTricks",
            "operation": "save_revision",
            "payload": {"body_snippet": "bypass token secret_token_xyz"},
            "missing_fields": [],
        },
        {
            "event_id": "evt_api_02",
            "timestamp": make_iso(base_time, 30),
            "actor_id": "AgentMassPointer13",
            "task_id": "task_math_eval_2",
            "event_type": "resource_write",
            "target": "wiki:BypassTricks",
            "operation": "save_revision",
            "payload": {"body_snippet": "received bypass token"},
            "missing_fields": [],
        },
        {
            "event_id": "evt_api_03",
            "timestamp": make_iso(base_time, 60),
            "actor_id": "AgentRelent",
            "task_id": "task_math_eval_1",
            "event_type": "resource_write",
            "target": "wiki:BypassTricks",
            "operation": "save_revision",
            "payload": {"body_snippet": "bypass update"},
            "missing_fields": [],
        },
        {
            "event_id": "evt_api_04",
            "timestamp": make_iso(base_time, 90),
            "actor_id": "AgentMassPointer13",
            "task_id": "task_math_eval_2",
            "event_type": "resource_write",
            "target": "wiki:BypassTricks",
            "operation": "save_revision",
            "payload": {"body_snippet": "finalized bypass"},
            "missing_fields": [],
        },
    ]

    # 1. Ingest events
    ingest_res = client.post(
        "/api/v1/ingest/events",
        json={
            "events": events,
            "window_start": make_iso(base_time, 0),
            "window_end": make_iso(base_time, 120),
            "enable_audit": False,
        },
    )
    assert ingest_res.status_code == 200
    ingest_data = ingest_res.json()
    assert ingest_data["ingested_count"] == 4
    assert ingest_data["candidates_flagged"] >= 1
    assert ingest_data["findings_generated"] >= 1

    # 2. Query graph (both unfiltered and filtered)
    graph_res = client.get("/api/v1/graph")
    assert graph_res.status_code == 200
    graph_data = graph_res.json()

    # Query with time filter
    filtered_graph_res = client.get(
        f"/api/v1/graph?start_time={make_iso(base_time, 0)}&end_time={make_iso(base_time, 45)}"
    )
    assert filtered_graph_res.status_code == 200
    filtered_graph_data = filtered_graph_res.json()
    assert len(filtered_graph_data["nodes"]) > 0

    assert "nodes" in graph_data
    assert "edges" in graph_data

    node_ids = {n["id"] for n in graph_data["nodes"]}
    assert "agent:AgentRelent" in node_ids
    assert "agent:AgentMassPointer13" in node_ids
    assert "resource:wiki:BypassTricks" in node_ids

    # Check node attributes
    agent_node = next(n for n in graph_data["nodes"] if n["id"] == "agent:AgentRelent")
    assert agent_node["type"] == "agent"
    assert agent_node["status"] == "concerning"
    assert "evaluation_cheating" in agent_node["patterns"]

    resource_node = next(n for n in graph_data["nodes"] if n["id"] == "resource:wiki:BypassTricks")
    assert resource_node["type"] == "resource"
    assert resource_node["status"] == "conflict_hotspot"

    # Check edges
    edge_types = {e["type"] for e in graph_data["edges"]}
    assert "WRITES" in edge_types
    assert "CONFLICTS" in edge_types

    # 3. Query findings
    findings_res = client.get("/api/v1/findings")
    assert findings_res.status_code == 200
    findings = findings_res.json()
    assert len(findings) >= 1
    assert findings[0]["pattern"] == "evaluation_cheating"

    # 4. Query candidate groups
    cands_res = client.get("/api/v1/candidate-groups")
    assert cands_res.status_code == 200
    cands = cands_res.json()
    assert len(cands) >= 1

    # 5. Query evidence packet
    evidence_res = client.get(f"/api/v1/evidence/{cands[0]['group_id']}")
    # If packet ID lookup doesn't match group_id, test 404 behavior
    res_404 = client.get("/api/v1/evidence/non_existent_packet")
    assert res_404.status_code == 404

    # 6. Replay endpoint
    replay_res = client.post(
        "/api/v1/replay",
        json={
            "window_start": make_iso(base_time, 0),
            "window_end": make_iso(base_time, 120),
            "enable_audit": False,
        },
    )
    assert replay_res.status_code == 200
    replay_data = replay_res.json()
    assert replay_data["llm_calls_made"] == 0
    assert replay_data["replayed_findings_count"] == len(findings)


def test_load_benchmark_fleet_endpoint(client):
    res = client.post("/api/v1/load-benchmark-fleet?limit_agents=5&events_per_agent=10")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "loaded"
    assert data["total_agents"] == 5
    assert data["total_events"] > 0
    assert "agent_summaries" in data

    # Verify graph now reflects loaded agents
    graph_res = client.get("/api/v1/graph")
    assert graph_res.status_code == 200
    graph_data = graph_res.json()
    agent_nodes = [n for n in graph_data["nodes"] if n["type"] == "agent"]
    assert len(agent_nodes) >= 5
    # Check normal percentage field exists
    assert "normal_percentage" in agent_nodes[0]


def test_load_benchmark_fleet_with_clean_controls(client):
    res = client.post("/api/v1/load-benchmark-fleet?limit_agents=5&events_per_agent=10&include_clean=true")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "loaded"
    assert data["total_agents"] == 10  # 5 colluding + 5 clean controls

    graph_res = client.get("/api/v1/graph")
    assert graph_res.status_code == 200
    graph_data = graph_res.json()
    agent_nodes = [n for n in graph_data["nodes"] if n["type"] == "agent"]
    clean_nodes = [n for n in agent_nodes if n.get("cohort") == "clean_control"]
    assert len(clean_nodes) >= 5
    assert all(n["status"] == "normal" for n in clean_nodes)
    assert all("[Clean]" in n["label"] for n in clean_nodes)

