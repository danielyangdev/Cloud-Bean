"""Tests for idempotent telemetry deduplication and bounded sliding window."""

import threading
from fastapi.testclient import TestClient
import pytest

from cloud_bean.api.app import create_app
from cloud_bean.ingestion.dedup import IdempotentEventDeduplicator
from cloud_bean.schemas.events import EventType, FleetEvent


def make_event(eid: str, actor: str = "agent-1") -> FleetEvent:
    return FleetEvent(
        event_id=eid,
        timestamp="2026-09-12T14:00:00Z",
        actor_id=actor,
        task_id="task-1",
        event_type=EventType.tool_call,
        target="endpoint/data",
    )


def test_dedup_initialization():
    with pytest.raises(ValueError, match="capacity must be at least 1"):
        IdempotentEventDeduplicator(capacity=0)

    dedup = IdempotentEventDeduplicator(capacity=100)
    assert dedup.size == 0


def test_filter_unique_and_duplicates():
    dedup = IdempotentEventDeduplicator(capacity=10)
    batch1 = [make_event("ev_1"), make_event("ev_2"), make_event("ev_3")]

    unique1, suppressed1 = dedup.filter_events(batch1)
    assert len(unique1) == 3
    assert suppressed1 == 0
    assert dedup.size == 3

    # Re-sending same batch: all should be suppressed
    unique2, suppressed2 = dedup.filter_events(batch1)
    assert len(unique2) == 0
    assert suppressed2 == 3

    # Mixed batch: 2 repeats + 2 new
    batch_mixed = [make_event("ev_2"), make_event("ev_4"), make_event("ev_3"), make_event("ev_5")]
    unique3, suppressed3 = dedup.filter_events(batch_mixed)
    assert [e.event_id for e in unique3] == ["ev_4", "ev_5"]
    assert suppressed3 == 2
    assert dedup.size == 5


def test_sliding_window_eviction():
    dedup = IdempotentEventDeduplicator(capacity=3)
    batch = [make_event("ev_1"), make_event("ev_2"), make_event("ev_3")]
    dedup.filter_events(batch)
    assert dedup.size == 3

    # Adding 4th event should evict ev_1
    dedup.filter_events([make_event("ev_4")])
    assert dedup.size == 3
    assert not dedup.is_duplicate("ev_1")
    assert dedup.is_duplicate("ev_2")
    assert dedup.is_duplicate("ev_3")
    assert dedup.is_duplicate("ev_4")

    # ev_1 can now be admitted again since it fell out of the window
    unique, suppressed = dedup.filter_events([make_event("ev_1")])
    assert len(unique) == 1
    assert suppressed == 0


def test_thread_safety():
    dedup = IdempotentEventDeduplicator(capacity=1000)
    num_threads = 8
    events_per_thread = 50

    def worker(worker_id: int):
        events = [make_event(f"ev_{worker_id}_{i}") for i in range(events_per_thread)]
        dedup.filter_events(events)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert dedup.size == num_threads * events_per_thread


def test_api_ingest_idempotency():
    app = create_app()
    client = TestClient(app)

    payload = {
        "events": [
            {
                "event_id": "api_ev_101",
                "timestamp": "2026-09-12T14:00:00Z",
                "actor_id": "agent-idemp",
                "task_id": "task-idemp",
                "event_type": "tool_call",
                "target": "wiki/test",
            },
            {
                "event_id": "api_ev_102",
                "timestamp": "2026-09-12T14:00:01Z",
                "actor_id": "agent-idemp",
                "task_id": "task-idemp",
                "event_type": "tool_call",
                "target": "wiki/test",
            },
        ]
    }

    # First ingest: both admitted
    res1 = client.post("/api/v1/ingest/events", json=payload)
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["ingested_count"] == 2
    assert data1["duplicates_suppressed"] == 0

    # Second ingest of identical batch: suppressed at API boundary
    res2 = client.post("/api/v1/ingest/events", json=payload)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["ingested_count"] == 0
    assert data2["duplicates_suppressed"] == 2
