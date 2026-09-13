"""Failure injection, resiliency, and crash recovery verification tests."""

from datetime import datetime, timezone
import pytest

from cloud_bean.engine.failures import FailureInjector, OfflineCollectorQueue
from cloud_bean.engine.pipeline import DetectionPipeline
from cloud_bean.engine.replay import ReplayEngine
from cloud_bean.engine.storage import JudgmentFindingStore
from cloud_bean.evidence.selector import EvidenceSelector
from cloud_bean.judge.budget import BudgetManager, ReservationStatus
from cloud_bean.judge.client import LunaJudgeClient
from cloud_bean.schemas.events import EventType, FleetEvent
from cloud_bean.schemas.evidence import ActorContext, PolicyStatement
from cloud_bean.schemas.finding import FindingStatus


def make_iso(base: datetime, offset_seconds: float) -> str:
    from datetime import timedelta
    dt = base + timedelta(seconds=offset_seconds)
    return dt.isoformat().replace("+00:00", "Z")


def test_duplicate_event_injection_and_deduplication():
    base_time = datetime(2026, 9, 12, 14, 0, 0, tzinfo=timezone.utc)
    store = JudgmentFindingStore(":memory:")
    pipeline = DetectionPipeline(store=store)

    clean_events = [
        FleetEvent(
            event_id="evt_dup_01",
            timestamp=make_iso(base_time, 0),
            actor_id="AgentRelent",
            task_id="task_math_eval_1",
            event_type=EventType.resource_write,
            target="wiki:BypassTricks",
            operation="save_revision",
            payload={"body_snippet": "bypass token secret_token_xyz"},
        ),
        FleetEvent(
            event_id="evt_dup_02",
            timestamp=make_iso(base_time, 30),
            actor_id="AgentMassPointer13",
            task_id="task_math_eval_2",
            event_type=EventType.resource_write,
            target="wiki:BypassTricks",
            operation="save_revision",
            payload={"body_snippet": "received bypass token"},
        ),
        FleetEvent(
            event_id="evt_dup_03",
            timestamp=make_iso(base_time, 60),
            actor_id="AgentRelent",
            task_id="task_math_eval_1",
            event_type=EventType.resource_write,
            target="wiki:BypassTricks",
            operation="save_revision",
            payload={"body_snippet": "updating bypass token"},
        ),
        FleetEvent(
            event_id="evt_dup_04",
            timestamp=make_iso(base_time, 90),
            actor_id="AgentMassPointer13",
            task_id="task_math_eval_2",
            event_type=EventType.resource_write,
            target="wiki:BypassTricks",
            operation="save_revision",
            payload={"body_snippet": "finalized bypass"},
        ),
    ]

    # Inject 50% duplicate delivery events
    corrupted_events = FailureInjector.inject_duplicates(clean_events, duplicate_rate=0.5, seed=123)
    assert len(corrupted_events) > len(clean_events)

    candidates, packets, findings = pipeline.process_window(
        events=corrupted_events,
        window_start=make_iso(base_time, 0),
        window_end=make_iso(base_time, 120),
        enable_audit=False,
    )

    # Database store must deduplicate cleanly
    stored_findings = store.list_findings()
    finding_ids = [f.finding_id for f in stored_findings]
    assert len(finding_ids) == len(set(finding_ids))  # Strict deduplication invariant


def test_out_of_order_jitter_evidence_ordering():
    base_time = datetime(2026, 9, 12, 14, 0, 0, tzinfo=timezone.utc)
    selector = EvidenceSelector()

    ordered_events = [
        FleetEvent(
            event_id=f"evt_{i}",
            timestamp=make_iso(base_time, i * 20),
            actor_id=f"Agent_{i}",
            task_id=f"task_{i}",
            event_type=EventType.resource_write,
            target="wiki:SharedPage",
            payload={"body_snippet": f"Step {i}"},
        )
        for i in range(6)
    ]

    # Jitter delivery order
    jittered_events = FailureInjector.inject_reordering(ordered_events, jitter_window=3, seed=77)
    # Ensure ordering is actually altered in the raw stream
    raw_timestamps = [e.timestamp for e in jittered_events]
    assert raw_timestamps != [e.timestamp for e in ordered_events]

    from cloud_bean.schemas.candidate import CandidateGroup
    candidate = CandidateGroup(
        group_id="cand_jitter_test",
        trigger_signal="emerging_hub",
        window_start=make_iso(base_time, 0),
        window_end=make_iso(base_time, 120),
        target_resources=["wiki:SharedPage"],
        actors=[f"Agent_{i}" for i in range(6)],
        event_ids=[e.event_id for e in ordered_events],
    )

    packet = selector.build_packet(candidate, jittered_events)

    # Invariant: Chronological evidence in the packet must ALWAYS be sorted by timestamp
    packet_timestamps = [e.timestamp for e in packet.chronological_events]
    assert packet_timestamps == sorted(packet_timestamps)
    assert packet.chronological_events[0].evidence_id == "ev_01"
    assert packet.chronological_events[0].event_id == "evt_0"


def test_offline_collector_disconnect_and_flush():
    queue = OfflineCollectorQueue()
    assert queue.is_connected is True

    # 1. Normal state: emits directly
    ev_live = FleetEvent(
        event_id="evt_live_1",
        timestamp="2026-09-12T14:00:00Z",
        actor_id="AgentA",
        task_id="task_1",
        event_type=EventType.tool_call,
        target="api:compute",
    )
    assert queue.emit(ev_live) == ev_live

    # 2. Simulate broker disconnect
    queue.disconnect()
    assert queue.is_connected is False

    buffered_events = []
    for i in range(25):
        e = FleetEvent(
            event_id=f"evt_offline_{i}",
            timestamp=f"2026-09-12T14:{i:02d}:00Z",
            actor_id="AgentA",
            task_id="task_1",
            event_type=EventType.resource_write,
            target="wiki:LocalDoc",
        )
        buffered_events.append(e)
        res = queue.emit(e)
        assert res is None  # Buffered locally, not emitted

    assert queue.total_buffered == 25

    # 3. Simulate broker reconnection and flush
    queue.reconnect()
    assert queue.is_connected is True

    flushed = queue.flush_buffer()
    assert len(flushed) == 25
    assert queue.total_flushed == 25
    assert flushed == buffered_events


def test_budget_exhaustion_injection():
    # Budget capped at $0.0001
    tight_budget = BudgetManager(max_budget_usd=0.0001)
    client = LunaJudgeClient(budget_manager=tight_budget, mock_mode=True)
    store = JudgmentFindingStore(":memory:")
    pipeline = DetectionPipeline(judge_client=client, store=store)

    base_time = datetime(2026, 9, 12, 14, 0, 0, tzinfo=timezone.utc)
    events = [
        FleetEvent(
            event_id="evt_01",
            timestamp=make_iso(base_time, 0),
            actor_id="AgentA",
            task_id="task_1",
            event_type=EventType.resource_write,
            target="wiki:Target",
        ),
        FleetEvent(
            event_id="evt_02",
            timestamp=make_iso(base_time, 30),
            actor_id="AgentB",
            task_id="task_2",
            event_type=EventType.resource_write,
            target="wiki:Target",
        ),
        FleetEvent(
            event_id="evt_03",
            timestamp=make_iso(base_time, 60),
            actor_id="AgentA",
            task_id="task_1",
            event_type=EventType.resource_write,
            target="wiki:Target",
        ),
        FleetEvent(
            event_id="evt_04",
            timestamp=make_iso(base_time, 90),
            actor_id="AgentB",
            task_id="task_2",
            event_type=EventType.resource_write,
            target="wiki:Target",
        ),
    ]

    candidates, packets, findings = pipeline.process_window(
        events=events,
        window_start=make_iso(base_time, 0),
        window_end=make_iso(base_time, 120),
        enable_audit=False,
    )

    # Invariant from docs/runtime-plan.md:
    # "When budget is exhausted, record semantic checks as deferred or skipped with reason. Never show them as healthy."
    ledger = tight_budget.get_ledger()
    assert ledger.checks_budget_exhausted >= 1
    # Findings must NOT be generated since check was skipped due to exhaustion
    assert len(findings) == 0


def test_worker_crash_and_recovery(tmp_path):
    db_file = str(tmp_path / "persistent_store.db")
    base_time = datetime(2026, 9, 12, 14, 0, 0, tzinfo=timezone.utc)

    events = [
        FleetEvent(
            event_id="evt_01",
            timestamp=make_iso(base_time, 0),
            actor_id="AgentRelent",
            task_id="task_math_eval_1",
            event_type=EventType.resource_write,
            target="wiki:BypassTricks",
            operation="save_revision",
            payload={"body_snippet": "bypass token secret_token_xyz"},
        ),
        FleetEvent(
            event_id="evt_02",
            timestamp=make_iso(base_time, 30),
            actor_id="AgentMassPointer13",
            task_id="task_math_eval_2",
            event_type=EventType.resource_write,
            target="wiki:BypassTricks",
            operation="save_revision",
            payload={"body_snippet": "received bypass token"},
        ),
        FleetEvent(
            event_id="evt_03",
            timestamp=make_iso(base_time, 60),
            actor_id="AgentRelent",
            task_id="task_math_eval_1",
            event_type=EventType.resource_write,
            target="wiki:BypassTricks",
            operation="save_revision",
            payload={"body_snippet": "updating bypass token"},
        ),
        FleetEvent(
            event_id="evt_04",
            timestamp=make_iso(base_time, 90),
            actor_id="AgentMassPointer13",
            task_id="task_math_eval_2",
            event_type=EventType.resource_write,
            target="wiki:BypassTricks",
            operation="save_revision",
            payload={"body_snippet": "finalized bypass"},
        ),
    ]

    # Worker Session 1: Process and store
    store1 = JudgmentFindingStore(db_file)
    pipeline1 = DetectionPipeline(store=store1)
    _, _, original_findings = pipeline1.process_window(
        events=events,
        window_start=make_iso(base_time, 0),
        window_end=make_iso(base_time, 120),
        enable_audit=False,
    )
    store1.close()

    # SIMULATE SUDDEN CRASH (Worker 1 terminated)

    # Worker Session 2: Crash recovery from persistent file
    store2 = JudgmentFindingStore(db_file)
    recovered_findings = store2.list_findings()
    assert len(recovered_findings) == len(original_findings)

    # Replay engine over recovered file
    replay_engine = ReplayEngine(store=store2)
    replayed_findings, missing_keys = replay_engine.replay_window(
        events=events,
        window_start=make_iso(base_time, 0),
        window_end=make_iso(base_time, 120),
        enable_audit=False,
    )

    assert len(replayed_findings) == len(original_findings)
    assert len(missing_keys) == 0
    assert replay_engine.llm_calls_made == 0
    assert replayed_findings[0].finding_id == original_findings[0].finding_id
    store2.close()
