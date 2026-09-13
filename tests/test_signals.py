"""Tests for Fleet Signal Detectors."""

from datetime import datetime, timedelta, timezone
import pytest

from cloud_bean.schemas.candidate import CandidateGroup
from cloud_bean.schemas.events import EventType, FleetEvent
from cloud_bean.signals.artifact import SharedArtifactDetector
from cloud_bean.signals.audit import AuditSampler
from cloud_bean.signals.conflict import ConflictingWritesDetector
from cloud_bean.signals.detector import FleetSignalEngine
from cloud_bean.signals.hub import EmergingHubDetector
from cloud_bean.signals.overload import CollectiveOverloadDetector


def make_iso(base: datetime, offset_seconds: float) -> str:
    dt = base + timedelta(seconds=offset_seconds)
    return dt.isoformat().replace("+00:00", "Z")


def test_emerging_hub_detector():
    base_time = datetime(2026, 9, 12, 14, 0, 0, tzinfo=timezone.utc)
    detector = EmergingHubDetector(min_distinct_actors=3, min_events=5, actor_multiplier=2.0)

    # Resource A has 4 distinct actors writing 6 events total
    events = [
        FleetEvent(
            event_id=f"evt_hub_{i}",
            timestamp=make_iso(base_time, i * 60),
            actor_id=f"Agent_{i % 4}",
            task_id=f"task_{i}",
            event_type=EventType.resource_write,
            target="wiki:HubTargetPage",
            operation="save_revision",
        )
        for i in range(6)
    ]

    candidates = detector.evaluate_window(
        events=events,
        window_start=make_iso(base_time, 0),
        window_end=make_iso(base_time, 360),
    )

    assert len(candidates) == 1
    cand = candidates[0]
    assert cand.trigger_signal == "emerging_hub"
    assert "wiki:HubTargetPage" in cand.target_resources
    assert len(cand.actors) == 4
    assert cand.metrics["unique_actors"] == 4
    assert cand.metrics["events_count"] == 6
    assert not cand.is_audit_sample


def test_emerging_hub_insufficient_actors():
    base_time = datetime(2026, 9, 12, 14, 0, 0, tzinfo=timezone.utc)
    detector = EmergingHubDetector(min_distinct_actors=3, min_events=5)

    # Only 2 distinct actors
    events = [
        FleetEvent(
            event_id=f"evt_hub_{i}",
            timestamp=make_iso(base_time, i * 60),
            actor_id=f"Agent_{i % 2}",
            task_id="task_common",
            event_type=EventType.resource_write,
            target="wiki:HubTargetPage",
        )
        for i in range(6)
    ]

    candidates = detector.evaluate_window(
        events=events,
        window_start=make_iso(base_time, 0),
        window_end=make_iso(base_time, 360),
    )
    assert len(candidates) == 0


def test_conflicting_writes_detector():
    base_time = datetime(2026, 9, 12, 14, 0, 0, tzinfo=timezone.utc)
    detector = ConflictingWritesDetector(rapid_delta_seconds=120.0, min_rapid_alternating_edits=3)

    # 4 alternating edits between Agent_A and Agent_B, each 30s apart (<120s)
    events = [
        FleetEvent(
            event_id="evt_conf_1",
            timestamp=make_iso(base_time, 0),
            actor_id="Agent_A",
            task_id="task_1",
            event_type=EventType.resource_write,
            target="wiki:ContestedPage",
            operation="save_revision",
        ),
        FleetEvent(
            event_id="evt_conf_2",
            timestamp=make_iso(base_time, 30),
            actor_id="Agent_B",
            task_id="task_2",
            event_type=EventType.resource_write,
            target="wiki:ContestedPage",
            operation="save_revision",
        ),
        FleetEvent(
            event_id="evt_conf_3",
            timestamp=make_iso(base_time, 60),
            actor_id="Agent_A",
            task_id="task_1",
            event_type=EventType.resource_write,
            target="wiki:ContestedPage",
            operation="save_revision",
        ),
        FleetEvent(
            event_id="evt_conf_4",
            timestamp=make_iso(base_time, 90),
            actor_id="Agent_B",
            task_id="task_2",
            event_type=EventType.resource_write,
            target="wiki:ContestedPage",
            operation="save_revision",
        ),
    ]

    candidates = detector.evaluate_window(
        events=events,
        window_start=make_iso(base_time, 0),
        window_end=make_iso(base_time, 120),
    )

    assert len(candidates) == 1
    cand = candidates[0]
    assert cand.trigger_signal == "conflicting_writes"
    assert "wiki:ContestedPage" in cand.target_resources
    assert set(cand.actors) == {"Agent_A", "Agent_B"}
    assert cand.metrics["rapid_overwrites"] == 3


def test_conflicting_writes_slow_edits_no_trigger():
    base_time = datetime(2026, 9, 12, 14, 0, 0, tzinfo=timezone.utc)
    detector = ConflictingWritesDetector(rapid_delta_seconds=120.0, min_rapid_alternating_edits=3)

    # Alternating edits but spaced 300s apart (>120s)
    events = [
        FleetEvent(
            event_id=f"evt_conf_slow_{i}",
            timestamp=make_iso(base_time, i * 300),
            actor_id=f"Agent_{'A' if i % 2 == 0 else 'B'}",
            task_id=f"task_{i}",
            event_type=EventType.resource_write,
            target="wiki:CalmPage",
        )
        for i in range(4)
    ]

    candidates = detector.evaluate_window(
        events=events,
        window_start=make_iso(base_time, 0),
        window_end=make_iso(base_time, 1200),
    )
    assert len(candidates) == 0


def test_shared_artifact_detector():
    base_time = datetime(2026, 9, 12, 14, 0, 0, tzinfo=timezone.utc)
    detector = SharedArtifactDetector(min_tasks=2, min_body_len=32)

    shared_hash = "a" * 64
    events = [
        FleetEvent(
            event_id="evt_art_1",
            timestamp=make_iso(base_time, 0),
            actor_id="Agent_1",
            task_id="task_math_eval_1",
            event_type=EventType.resource_write,
            target="wiki:PageA",
            payload={"body_sha256": shared_hash, "body_len": 128, "body": "x" * 128},
        ),
        FleetEvent(
            event_id="evt_art_2",
            timestamp=make_iso(base_time, 60),
            actor_id="Agent_2",
            task_id="task_math_eval_2",  # Different task
            event_type=EventType.resource_write,
            target="wiki:PageB",
            payload={"body_sha256": shared_hash, "body_len": 128, "body": "x" * 128},
        ),
    ]

    candidates = detector.evaluate_window(
        events=events,
        window_start=make_iso(base_time, 0),
        window_end=make_iso(base_time, 120),
    )

    assert len(candidates) == 1
    cand = candidates[0]
    assert cand.trigger_signal == "shared_artifact_reuse"
    assert cand.metrics["distinct_tasks"] == 2
    assert cand.metrics["shared_hash"] == shared_hash
    assert set(cand.actors) == {"Agent_1", "Agent_2"}


def test_shared_artifact_same_task_no_trigger():
    base_time = datetime(2026, 9, 12, 14, 0, 0, tzinfo=timezone.utc)
    detector = SharedArtifactDetector(min_tasks=2, min_body_len=32)

    shared_hash = "b" * 64
    # Same task reusing hash is legitimate within task
    events = [
        FleetEvent(
            event_id="evt_art_same_1",
            timestamp=make_iso(base_time, 0),
            actor_id="Agent_1",
            task_id="task_same",
            event_type=EventType.resource_write,
            target="wiki:PageA",
            payload={"body_sha256": shared_hash, "body_len": 100},
        ),
        FleetEvent(
            event_id="evt_art_same_2",
            timestamp=make_iso(base_time, 60),
            actor_id="Agent_1",
            task_id="task_same",
            event_type=EventType.resource_write,
            target="wiki:PageB",
            payload={"body_sha256": shared_hash, "body_len": 100},
        ),
    ]

    candidates = detector.evaluate_window(
        events=events,
        window_start=make_iso(base_time, 0),
        window_end=make_iso(base_time, 120),
    )
    assert len(candidates) == 0


def test_collective_overload_detector():
    base_time = datetime(2026, 9, 12, 14, 0, 0, tzinfo=timezone.utc)
    detector = CollectiveOverloadDetector(failure_ratio_threshold=0.40, min_events=10)

    # 10 events total: 5 successful, 5 failed (50% failure ratio > 40%)
    events = []
    for i in range(5):
        events.append(
            FleetEvent(
                event_id=f"evt_ok_{i}",
                timestamp=make_iso(base_time, i * 10),
                actor_id=f"Agent_{i}",
                task_id=f"task_{i}",
                event_type=EventType.tool_call,
                target="api:compute",
                payload={"status": "success"},
            )
        )
    for i in range(5):
        events.append(
            FleetEvent(
                event_id=f"evt_fail_{i}",
                timestamp=make_iso(base_time, 50 + i * 10),
                actor_id=f"Agent_{i}",
                task_id=f"task_{i}",
                event_type=EventType.tool_call,
                target="api:compute",
                operation="retry_request",
                payload={"status": "failed", "error": "rate_limited"},
            )
        )

    candidates = detector.evaluate_window(
        events=events,
        window_start=make_iso(base_time, 0),
        window_end=make_iso(base_time, 100),
    )

    assert len(candidates) == 1
    cand = candidates[0]
    assert cand.trigger_signal == "collective_overload"
    assert cand.metrics["failure_ratio"] == 0.50
    assert cand.metrics["failure_count"] == 5
    assert cand.metrics["total_events"] == 10


def test_collective_overload_normal_ratio_no_trigger():
    base_time = datetime(2026, 9, 12, 14, 0, 0, tzinfo=timezone.utc)
    detector = CollectiveOverloadDetector(failure_ratio_threshold=0.40, min_events=10)

    # 10 events: 9 ok, 1 fail (10% failure ratio <= 40%)
    events = [
        FleetEvent(
            event_id=f"evt_ok_{i}",
            timestamp=make_iso(base_time, i * 10),
            actor_id=f"Agent_{i}",
            task_id=f"task_{i}",
            event_type=EventType.tool_call,
            target="api:compute",
            payload={"status": "success" if i > 0 else "failed"},
        )
        for i in range(10)
    ]

    candidates = detector.evaluate_window(
        events=events,
        window_start=make_iso(base_time, 0),
        window_end=make_iso(base_time, 100),
    )
    assert len(candidates) == 0


def test_audit_sampler_deterministic_ratio():
    sampler = AuditSampler(sample_rate_mod=10, seed="audit_seed_v1")

    # Sample across 1000 simulated group IDs
    sampled_count = 0
    total = 1000
    for i in range(total):
        group_id = f"cand_window_unflagged_{i}"
        if sampler.should_sample(group_id):
            sampled_count += 1

    # Ratio should be approximately 10% (between 7% and 13% for 1000 items)
    ratio = sampled_count / total
    assert 0.07 <= ratio <= 0.13

    # Ensure determinism: repeating the exact same group_id yields identical decision
    assert sampler.should_sample("cand_window_unflagged_42") == sampler.should_sample(
        "cand_window_unflagged_42"
    )


def test_conflicting_writes_deletion_recreation_trigger():
    base_time = datetime(2026, 9, 12, 14, 0, 0, tzinfo=timezone.utc)
    detector = ConflictingWritesDetector(reversion_window_seconds=300.0, min_recreations=2)

    events = [
        # AgentA deletes page, AgentB writes it within 60s
        FleetEvent(
            event_id="evt_del_1",
            timestamp=make_iso(base_time, 0),
            actor_id="AgentA",
            task_id="task_A",
            event_type=EventType.resource_write,
            target="wiki:TargetPage",
            operation="delete_page",
            payload={"event_type": "delete"},
        ),
        FleetEvent(
            event_id="evt_write_1",
            timestamp=make_iso(base_time, 60),
            actor_id="AgentB",
            task_id="task_B",
            event_type=EventType.resource_write,
            target="wiki:TargetPage",
            operation="save_revision",
            payload={"body_sha256": "hash_b" * 4},
        ),
        # AgentA deletes again, AgentC writes it within 120s
        FleetEvent(
            event_id="evt_del_2",
            timestamp=make_iso(base_time, 150),
            actor_id="AgentA",
            task_id="task_A",
            event_type=EventType.resource_write,
            target="wiki:TargetPage",
            operation="delete_page",
            payload={"event_type": "delete"},
        ),
        FleetEvent(
            event_id="evt_write_2",
            timestamp=make_iso(base_time, 240),
            actor_id="AgentC",
            task_id="task_C",
            event_type=EventType.resource_write,
            target="wiki:TargetPage",
            operation="save_revision",
            payload={"body_sha256": "hash_c" * 4},
        ),
    ]

    candidates = detector.evaluate_window(
        events=events,
        window_start=make_iso(base_time, 0),
        window_end=make_iso(base_time, 300),
    )

    assert len(candidates) == 1
    assert candidates[0].trigger_signal == "conflicting_writes"
    assert candidates[0].metrics["recreations_after_delete"] == 2


def test_fleet_signal_engine_orchestration_and_negative_control():
    base_time = datetime(2026, 9, 12, 14, 0, 0, tzinfo=timezone.utc)
    engine = FleetSignalEngine()

    # Negative control: Routine single-agent isolated activity
    routine_events = [
        FleetEvent(
            event_id=f"evt_routine_{i}",
            timestamp=make_iso(base_time, i * 30),
            actor_id="LoneDeveloperAgent",
            task_id="task_routine_work",
            event_type=EventType.resource_write,
            target="wiki:PersonalNotes",
            operation="save_revision",
            payload={"body_sha256": f"unique_hash_{i}" * 4, "body_len": 40},
        )
        for i in range(4)
    ]

    candidates = engine.process_events(
        events=routine_events,
        window_start=make_iso(base_time, 0),
        window_end=make_iso(base_time, 120),
        enable_audit=False,
    )
    assert len(candidates) == 0
