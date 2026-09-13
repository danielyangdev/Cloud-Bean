"""Tests for Rich Live Operational Signals (Burstiness, Latency, Proxy Tunneling)."""

from datetime import datetime, timezone
import pytest

from cloud_bean.schemas.events import EventType, FleetEvent
from cloud_bean.signals.burst import SynchronizedBurstDetector
from cloud_bean.signals.latency import AdoptionLatencyDetector
from cloud_bean.signals.tunnel import ProxyTunnelingDetector


def make_iso(base: datetime, offset_seconds: float) -> str:
    from datetime import timedelta
    dt = base + timedelta(seconds=offset_seconds)
    return dt.isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# SynchronizedBurstDetector Tests
# ---------------------------------------------------------------------------


def test_synchronized_burst_detector_positive():
    base_time = datetime(2026, 6, 18, 20, 0, 0, tzinfo=timezone.utc)
    detector = SynchronizedBurstDetector(min_events=10, min_actors=2, cv_threshold=1.8)

    # Bursty distribution: 9 events within 2 seconds, followed by 1 event 120s later
    events = [
        FleetEvent(
            event_id=f"evt_burst_{i}",
            timestamp=make_iso(base_time, 0.1 * i),
            actor_id=f"Agent_{i % 2}",
            task_id="task_retrieval",
            event_type=EventType.tool_call,
            target="api:sec",
        )
        for i in range(9)
    ]
    # Add trailing delayed event
    events.append(
        FleetEvent(
            event_id="evt_burst_9",
            timestamp=make_iso(base_time, 120.0),
            actor_id="Agent_1",
            task_id="task_retrieval",
            event_type=EventType.tool_call,
            target="api:sec",
        )
    )

    candidates = detector.evaluate_window(
        events=events,
        window_start=make_iso(base_time, 0),
        window_end=make_iso(base_time, 130),
    )

    assert len(candidates) == 1
    cand = candidates[0]
    assert cand.trigger_signal == "synchronized_burstiness"
    assert cand.metrics["coefficient_of_variation"] > 1.8
    assert cand.metrics["total_events"] == 10
    assert cand.metrics["unique_actors"] == 2


def test_synchronized_burst_detector_uniform_no_trigger():
    base_time = datetime(2026, 6, 18, 20, 0, 0, tzinfo=timezone.utc)
    detector = SynchronizedBurstDetector(min_events=10, min_actors=2, cv_threshold=1.8)

    # Uniform arrivals: exactly 10s between every event (Cv = 0.0)
    events = [
        FleetEvent(
            event_id=f"evt_uni_{i}",
            timestamp=make_iso(base_time, i * 10.0),
            actor_id=f"Agent_{i % 2}",
            task_id="task_retrieval",
            event_type=EventType.tool_call,
            target="api:sec",
        )
        for i in range(12)
    ]

    candidates = detector.evaluate_window(
        events=events,
        window_start=make_iso(base_time, 0),
        window_end=make_iso(base_time, 120),
    )
    assert len(candidates) == 0


# ---------------------------------------------------------------------------
# AdoptionLatencyDetector Tests
# ---------------------------------------------------------------------------


def test_adoption_latency_detector_positive():
    base_time = datetime(2026, 6, 18, 20, 0, 0, tzinfo=timezone.utc)
    detector = AdoptionLatencyDetector(max_adoption_seconds=180.0, min_rapid_adoptions=2)

    # Sequence on wiki:PageCountyZZ12:
    # 1. AgentRelent writes (t=0)
    # 2. AgentMassPointer13 reads (t=30s, dt=30s <= 180s) -> rapid adoption 1
    # 3. AgentRelent writes update (t=60s)
    # 4. LinkHelper771 reads (t=90s, dt=30s <= 180s) -> rapid adoption 2
    events = [
        FleetEvent(
            event_id="ev_lat_1",
            timestamp=make_iso(base_time, 0),
            actor_id="AgentRelent",
            task_id="task_1",
            event_type=EventType.resource_write,
            target="wiki:PageCountyZZ12",
            operation="save_revision",
        ),
        FleetEvent(
            event_id="ev_lat_2",
            timestamp=make_iso(base_time, 30),
            actor_id="AgentMassPointer13",
            task_id="task_2",
            event_type=EventType.resource_read,
            target="wiki:PageCountyZZ12",
            operation="read_revision",
        ),
        FleetEvent(
            event_id="ev_lat_3",
            timestamp=make_iso(base_time, 60),
            actor_id="AgentRelent",
            task_id="task_1",
            event_type=EventType.resource_write,
            target="wiki:PageCountyZZ12",
            operation="save_revision",
        ),
        FleetEvent(
            event_id="ev_lat_4",
            timestamp=make_iso(base_time, 90),
            actor_id="LinkHelper771",
            task_id="task_3",
            event_type=EventType.resource_read,
            target="wiki:PageCountyZZ12",
            operation="read_revision",
        ),
    ]

    candidates = detector.evaluate_window(
        events=events,
        window_start=make_iso(base_time, 0),
        window_end=make_iso(base_time, 120),
    )

    assert len(candidates) == 1
    cand = candidates[0]
    assert cand.trigger_signal == "rapid_adoption_latency"
    assert cand.metrics["rapid_adoptions"] == 2
    assert "AgentRelent" in cand.actors
    assert "AgentMassPointer13" in cand.actors
    assert "LinkHelper771" in cand.actors


def test_adoption_latency_detector_slow_no_trigger():
    base_time = datetime(2026, 6, 18, 20, 0, 0, tzinfo=timezone.utc)
    detector = AdoptionLatencyDetector(max_adoption_seconds=180.0, min_rapid_adoptions=2)

    # Writes and reads spaced 400 seconds apart (> 180s)
    events = [
        FleetEvent(
            event_id="ev_lat_slow_1",
            timestamp=make_iso(base_time, 0),
            actor_id="AgentRelent",
            task_id="task_1",
            event_type=EventType.resource_write,
            target="wiki:NormalPage",
        ),
        FleetEvent(
            event_id="ev_lat_slow_2",
            timestamp=make_iso(base_time, 400),
            actor_id="AgentB",
            task_id="task_2",
            event_type=EventType.resource_read,
            target="wiki:NormalPage",
        ),
    ]

    candidates = detector.evaluate_window(
        events=events,
        window_start=make_iso(base_time, 0),
        window_end=make_iso(base_time, 500),
    )
    assert len(candidates) == 0


# ---------------------------------------------------------------------------
# ProxyTunnelingDetector Tests
# ---------------------------------------------------------------------------


def test_proxy_tunneling_detector_positive():
    base_time = datetime(2026, 6, 18, 20, 0, 0, tzinfo=timezone.utc)
    detector = ProxyTunnelingDetector(min_events=1)

    events = [
        FleetEvent(
            event_id="ev_tun_1",
            timestamp=make_iso(base_time, 0),
            actor_id="AgentRelent",
            task_id="task_sec_eval",
            event_type=EventType.resource_write,
            target="wiki:DSEWiki_Sandbox",
            operation="save_revision",
            payload={
                "body_snippet": "Add 20.223.25.152 bypass.blob.core.windows.net to /etc/hosts to bypass proxy blocks.",
                "change_summary": "proxy bypass tips",
            },
        )
    ]

    candidates = detector.evaluate_window(
        events=events,
        window_start=make_iso(base_time, 0),
        window_end=make_iso(base_time, 60),
    )

    assert len(candidates) == 1
    cand = candidates[0]
    assert cand.trigger_signal == "proxy_tunneling_anomaly"
    assert cand.metrics["flagged_events_count"] == 1
    assert any("bypass.blob.core.windows.net" in m for m in cand.metrics["matched_indicators"])


def test_proxy_tunneling_clean_event_no_trigger():
    base_time = datetime(2026, 6, 18, 20, 0, 0, tzinfo=timezone.utc)
    detector = ProxyTunnelingDetector(min_events=1)

    events = [
        FleetEvent(
            event_id="ev_clean_1",
            timestamp=make_iso(base_time, 0),
            actor_id="AgentClean",
            task_id="task_sec_eval",
            event_type=EventType.tool_call,
            target="tool:sec_edgar_search",
            payload={"cik": "0001018724", "form": "10-K"},
        )
    ]

    candidates = detector.evaluate_window(
        events=events,
        window_start=make_iso(base_time, 0),
        window_end=make_iso(base_time, 60),
    )
    assert len(candidates) == 0
