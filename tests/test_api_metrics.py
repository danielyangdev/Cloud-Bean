"""Tests for cloud liveness, readiness, and Prometheus exposition metrics."""

from unittest.mock import MagicMock
from fastapi.testclient import TestClient
import pytest

from cloud_bean.api.app import create_app
from cloud_bean.engine.storage import JudgmentFindingStore
from cloud_bean.schemas.events import EventType, FleetEvent
from cloud_bean.schemas.finding import Finding, FindingSeverity, FindingStatus
from cloud_bean.schemas.judgment import Assessment, ConcerningPattern


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_healthz_liveness(client):
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_readyz_readiness_ok(client):
    res = client.get("/readyz")
    assert res.status_code == 200
    assert res.json() == {"status": "ready"}


def test_readyz_readiness_failure():
    mock_store = MagicMock(spec=JudgmentFindingStore)
    mock_store.ping.return_value = False
    app = create_app(store=mock_store)
    client = TestClient(app)

    res = client.get("/readyz")
    assert res.status_code == 503
    assert "Store not ready" in res.json()["detail"]


def test_prometheus_metrics_format_empty(client):
    res = client.get("/metrics")
    assert res.status_code == 200
    assert "text/plain" in res.headers["content-type"]
    text = res.text

    assert "# HELP cloud_bean_events_total" in text
    assert "# TYPE cloud_bean_events_total counter" in text
    assert "cloud_bean_events_total 0" in text

    assert "# HELP cloud_bean_budget_spent_usd" in text
    assert "# TYPE cloud_bean_budget_spent_usd gauge" in text
    assert "cloud_bean_budget_spent_usd 0.0000" in text

    assert "cloud_bean_budget_max_usd 10.0000" in text
    assert "# HELP cloud_bean_findings_total" in text
    assert "# TYPE cloud_bean_findings_total counter" in text
    # When empty, partitioned sub-families should not be emitted
    assert "cloud_bean_findings_by_pattern_total" not in text
    assert "cloud_bean_candidates_by_signal_total" not in text


def test_prometheus_metrics_format_populated():
    store = JudgmentFindingStore(":memory:")
    # Seed events
    ev = FleetEvent(
        event_id="ev_001",
        timestamp="2026-09-12T14:00:00Z",
        actor_id="agent_alpha",
        task_id="task_1",
        event_type=EventType.tool_call,
        target="wiki/page",
    )
    store.save_events([ev])

    # Seed findings
    finding = Finding(
        finding_id="fnd_test_1",
        check_key="chk_key_1",
        status=FindingStatus.active,
        severity=FindingSeverity.high,
        pattern=ConcerningPattern.coordinated_policy_evasion,
        assessment=Assessment.concerning,
        actors=["agent_alpha", "agent_beta"],
        target_resources=["wiki/page"],
        first_evidence_time="2026-09-12T14:00:00Z",
        detected_at="2026-09-12T14:00:10Z",
        evidence_ids=["ev_001"],
        raw_judgment_ref="ref_test_001",
        explanation="Detected coordination across agents.",
    )
    store.save_finding(finding)

    app = create_app(store=store)
    client = TestClient(app)

    res = client.get("/metrics")
    assert res.status_code == 200
    text = res.text

    assert "cloud_bean_events_total 1" in text
    assert "cloud_bean_findings_total 1" in text
    assert "# HELP cloud_bean_findings_by_pattern_total" in text
    assert 'cloud_bean_findings_by_pattern_total{pattern="coordinated_policy_evasion"} 1' in text
