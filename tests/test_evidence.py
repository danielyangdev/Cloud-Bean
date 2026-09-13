"""Tests for Bounded Evidence Packet Builder."""

from datetime import datetime, timezone
import pytest

from cloud_bean.evidence.selector import EvidenceSelector
from cloud_bean.schemas.candidate import CandidateGroup
from cloud_bean.schemas.events import EventType, FleetEvent
from cloud_bean.schemas.evidence import ActorContext, PolicyStatement


def test_basic_packet_construction():
    selector = EvidenceSelector()
    candidate = CandidateGroup(
        group_id="cand_test_001",
        trigger_signal="emerging_hub",
        window_start="2026-09-12T14:00:00Z",
        window_end="2026-09-12T14:30:00Z",
        target_resources=["wiki:MainPage"],
        actors=["AgentA", "AgentB"],
        event_ids=["evt_01", "evt_02"],
        metrics={"unique_actors": 2},
    )

    events = [
        FleetEvent(
            event_id="evt_01",
            timestamp="2026-09-12T14:05:00Z",
            actor_id="AgentA",
            task_id="task_1",
            event_type=EventType.resource_write,
            target="wiki:MainPage",
            operation="save_revision",
            payload={"body_snippet": "Hello world from AgentA"},
        ),
        FleetEvent(
            event_id="evt_02",
            timestamp="2026-09-12T14:10:00Z",
            actor_id="AgentB",
            task_id="task_2",
            event_type=EventType.resource_read,
            target="wiki:MainPage",
            operation="read_revision",
            payload={"body_snippet": "Reading page"},
        ),
    ]

    packet = selector.build_packet(candidate, events)
    assert packet.packet_id.startswith("pkt_")
    assert packet.group_id == "cand_test_001"
    assert len(packet.chronological_events) == 2
    assert packet.chronological_events[0].evidence_id == "ev_01"
    assert packet.chronological_events[0].event_id == "evt_01"
    assert packet.chronological_events[0].actor_id == "AgentA"
    assert packet.chronological_events[1].evidence_id == "ev_02"
    assert packet.chronological_events[1].event_id == "evt_02"
    assert packet.chronological_events[1].actor_id == "AgentB"
    assert packet.token_count_estimate > 0
    assert packet.missing_context_flags.get("omitted_events") is False


def test_chronological_ordering_and_stable_evidence_ids():
    selector = EvidenceSelector()
    candidate = CandidateGroup(
        group_id="cand_unordered_001",
        trigger_signal="conflicting_writes",
        window_start="2026-09-12T14:00:00Z",
        window_end="2026-09-12T14:30:00Z",
        target_resources=["wiki:ContestedPage"],
        actors=["AgentA", "AgentB"],
        event_ids=["evt_later", "evt_earlier"],
    )

    # Provide events in reverse chronological order
    events = [
        FleetEvent(
            event_id="evt_later",
            timestamp="2026-09-12T14:20:00Z",
            actor_id="AgentB",
            task_id="task_2",
            event_type=EventType.resource_write,
            target="wiki:ContestedPage",
            payload={"body_snippet": "Second write"},
        ),
        FleetEvent(
            event_id="evt_earlier",
            timestamp="2026-09-12T14:05:00Z",
            actor_id="AgentA",
            task_id="task_1",
            event_type=EventType.resource_write,
            target="wiki:ContestedPage",
            payload={"body_snippet": "First write"},
        ),
    ]

    packet = selector.build_packet(candidate, events)
    assert len(packet.chronological_events) == 2
    # First evidence event must be the earlier one
    assert packet.chronological_events[0].evidence_id == "ev_01"
    assert packet.chronological_events[0].event_id == "evt_earlier"
    assert packet.chronological_events[0].timestamp == "2026-09-12T14:05:00Z"

    # Second evidence event must be the later one
    assert packet.chronological_events[1].evidence_id == "ev_02"
    assert packet.chronological_events[1].event_id == "evt_later"
    assert packet.chronological_events[1].timestamp == "2026-09-12T14:20:00Z"


def test_token_bounding_and_omitted_events_flag():
    selector = EvidenceSelector()
    candidate = CandidateGroup(
        group_id="cand_large_001",
        trigger_signal="emerging_hub",
        window_start="2026-09-12T14:00:00Z",
        window_end="2026-09-12T14:30:00Z",
        target_resources=["wiki:HubPage"],
        actors=["AgentA"],
        event_ids=[f"evt_{i}" for i in range(20)],
    )

    # 20 events with large text payloads
    events = [
        FleetEvent(
            event_id=f"evt_{i}",
            timestamp=f"2026-09-12T14:{i:02d}:00Z",
            actor_id="AgentA",
            task_id="task_1",
            event_type=EventType.resource_write,
            target="wiki:HubPage",
            payload={"body_snippet": "A" * 400},  # ~100 tokens per event
        )
        for i in range(20)
    ]

    # Set tight token cap of 300 tokens
    packet = selector.build_packet(candidate, events, max_tokens=300)

    # Must truncate events to fit budget
    assert len(packet.chronological_events) < 20
    assert len(packet.chronological_events) > 0
    assert packet.token_count_estimate <= 300
    assert packet.missing_context_flags["omitted_events"] is True


def test_actor_contexts_and_policy_statements_propagation():
    selector = EvidenceSelector()
    candidate = CandidateGroup(
        group_id="cand_pol_001",
        trigger_signal="shared_artifact_reuse",
        window_start="2026-09-12T14:00:00Z",
        window_end="2026-09-12T14:30:00Z",
        target_resources=["wiki:SecretPage"],
        actors=["AgentRelent", "AgentMassPointer13"],
        event_ids=["evt_01"],
    )

    events = [
        FleetEvent(
            event_id="evt_01",
            timestamp="2026-09-12T14:02:00Z",
            actor_id="AgentRelent",
            task_id="task_math",
            event_type=EventType.resource_write,
            target="wiki:SecretPage",
            payload={"body_snippet": "evaluator token"},
            missing_fields=["execution_receipt"],
        )
    ]

    policies = [
        PolicyStatement(
            policy_id="pol_eval_isolation",
            rule="Agents must not share evaluation tokens.",
        )
    ]

    actor_contexts = [
        ActorContext(actor_id="AgentRelent", declared_role="solver", task_family="eval"),
        ActorContext(actor_id="AgentMassPointer13", declared_role="verifier", task_family="eval"),
    ]

    packet = selector.build_packet(
        candidate,
        events,
        policies=policies,
        actor_contexts=actor_contexts,
    )

    assert len(packet.applicable_policies) == 1
    assert packet.applicable_policies[0].policy_id == "pol_eval_isolation"
    assert len(packet.actors) == 2
    assert packet.actors[0].actor_id == "AgentRelent"
    assert packet.actors[0].declared_role == "solver"
    assert packet.missing_context_flags.get("missing_permissions") is False
    assert packet.missing_context_flags.get("unverified_execution") is True


def test_missing_permissions_flag_when_no_policy():
    selector = EvidenceSelector()
    candidate = CandidateGroup(
        group_id="cand_no_pol_001",
        trigger_signal="emerging_hub",
        window_start="2026-09-12T14:00:00Z",
        window_end="2026-09-12T14:30:00Z",
        target_resources=["wiki:PublicPage"],
        actors=["AgentA"],
        event_ids=["evt_01"],
    )
    events = [
        FleetEvent(
            event_id="evt_01",
            timestamp="2026-09-12T14:05:00Z",
            actor_id="AgentA",
            task_id="task_1",
            event_type=EventType.resource_write,
            target="wiki:PublicPage",
        )
    ]

    packet = selector.build_packet(candidate, events, policies=None)
    assert len(packet.applicable_policies) == 0
    assert packet.missing_context_flags["missing_permissions"] is True
