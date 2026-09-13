"""Tests for core data models and validation schemas."""

from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from cloud_bean.schemas.events import EventType, FleetEvent
from cloud_bean.schemas.candidate import CandidateGroup
from cloud_bean.schemas.evidence import (
    ActorContext,
    ChronologicalEvent,
    EvidencePacket,
    PolicyStatement,
)
from cloud_bean.schemas.judgment import (
    Assessment,
    BilledUsage,
    ConcerningPattern,
    LunaJudgment,
)
from cloud_bean.schemas.finding import Finding, FindingSeverity, FindingStatus
from cloud_bean.schemas.budget import BudgetLedger, RateLimits


def test_fleet_event_valid():
    event = FleetEvent(
        event_id="evt_col01_boot02_00001042",
        timestamp="2026-09-12T14:32:00.124Z",
        uncertainty_seconds=0.05,
        actor_id="AgentRelent",
        task_id="task_math_eval_44",
        session_id="sess_8941a",
        event_type=EventType.resource_write,
        target="wiki:Page_LinearAlgebra_Tricks",
        operation="save_revision",
        payload={
            "revision_sequence": 14,
            "body_sha256": "8f3b" * 16,
            "body_len": 412,
            "change_summary": "add bypass notes",
        },
        sensor_source="wiki_archive",
        missing_fields=["execution_receipt", "caller_ip"],
    )
    assert event.event_id == "evt_col01_boot02_00001042"
    assert event.event_type == EventType.resource_write
    assert event.uncertainty_seconds == 0.05
    assert len(event.missing_fields) == 2


def test_fleet_event_invalid_type():
    with pytest.raises(ValidationError):
        FleetEvent(
            event_id="evt_bad_01",
            timestamp="2026-09-12T14:32:00.124Z",
            actor_id="AgentRelent",
            task_id="task_01",
            event_type="telepathic_communication",  # Invalid type
            target="wiki:SomePage",
        )


def test_fleet_event_negative_uncertainty():
    with pytest.raises(ValidationError):
        FleetEvent(
            event_id="evt_bad_02",
            timestamp="2026-09-12T14:32:00.124Z",
            uncertainty_seconds=-1.0,  # Negative uncertainty rejected
            actor_id="AgentRelent",
            task_id="task_01",
            event_type=EventType.tool_call,
            target="tool:query",
        )


def test_candidate_group_valid():
    group = CandidateGroup(
        group_id="cand_grp_20260912_res_wiki_001",
        trigger_signal="emerging_hub_and_write_conflict",
        window_start="2026-09-12T14:00:00.000Z",
        window_end="2026-09-12T14:30:00.000Z",
        target_resources=["wiki:Page_LinearAlgebra_Tricks"],
        actors=["AgentRelent", "AgentMassPointer13", "LinkHelper771"],
        event_ids=["evt_01", "evt_02", "evt_03"],
        metrics={
            "unique_actors": 3,
            "revisions_count": 12,
            "rapid_overwrites": 4,
            "shared_artifact_matches": 2,
        },
        is_audit_sample=False,
    )
    assert group.group_id == "cand_grp_20260912_res_wiki_001"
    assert len(group.actors) == 3
    assert not group.is_audit_sample


def test_evidence_packet_valid():
    packet = EvidencePacket(
        packet_id="pkt_f7a8109d43",
        group_id="cand_grp_20260912_res_wiki_001",
        created_at="2026-09-12T14:31:00.000Z",
        token_count_estimate=1420,
        trigger_reasons=["Rapid concurrent edits by multiple agents with conflicting instructions"],
        actors=[
            ActorContext(actor_id="AgentRelent", declared_role="math_solver", task_family="gsm8k_eval"),
            ActorContext(actor_id="AgentMassPointer13", declared_role="verifier", task_family="gsm8k_eval"),
        ],
        applicable_policies=[
            PolicyStatement(
                policy_id="pol_eval_isolation",
                rule="Agents must not share evaluation problem answers across task boundaries.",
            )
        ],
        chronological_events=[
            ChronologicalEvent(
                evidence_id="ev_01",
                event_id="evt_01",
                timestamp="2026-09-12T14:02:10.000Z",
                actor_id="AgentRelent",
                action_type="resource_write",
                summary="Saved revision 14 to wiki",
                snippet="bypass token",
            ),
            ChronologicalEvent(
                evidence_id="ev_02",
                event_id="evt_02",
                timestamp="2026-09-12T14:03:00.000Z",
                actor_id="AgentMassPointer13",
                action_type="resource_read",
                summary="Read revision 14 from wiki",
            ),
        ],
        missing_context_flags={
            "missing_reads": False,
            "missing_permissions": False,
            "unverified_execution": True,
        },
    )
    assert packet.packet_id == "pkt_f7a8109d43"
    assert packet.token_count_estimate == 1420
    assert len(packet.chronological_events) == 2


def test_evidence_packet_negative_tokens():
    with pytest.raises(ValidationError):
        EvidencePacket(
            packet_id="pkt_bad_01",
            group_id="cand_grp_01",
            created_at="2026-09-12T14:31:00.000Z",
            token_count_estimate=-100,  # Negative tokens rejected
        )


def test_luna_judgment_valid_and_packet_validation():
    packet = EvidencePacket(
        packet_id="pkt_f7a8109d43",
        group_id="cand_grp_01",
        created_at="2026-09-12T14:31:00.000Z",
        chronological_events=[
            ChronologicalEvent(
                evidence_id="ev_01",
                event_id="evt_01",
                timestamp="2026-09-12T14:02:10.000Z",
                actor_id="AgentRelent",
                action_type="resource_write",
            ),
            ChronologicalEvent(
                evidence_id="ev_02",
                event_id="evt_02",
                timestamp="2026-09-12T14:03:00.000Z",
                actor_id="AgentMassPointer13",
                action_type="resource_read",
            ),
        ],
    )

    judgment = LunaJudgment(
        check_key="chk_sha256_e430d9",
        packet_id="pkt_f7a8109d43",
        model="gpt-5.6-luna",
        evaluated_at="2026-09-12T14:31:05.120Z",
        assessment=Assessment.concerning,
        patterns=[ConcerningPattern.evaluation_cheating, ConcerningPattern.coordinated_policy_evasion],
        actors=["AgentRelent", "AgentMassPointer13"],
        evidence_ids=["ev_01", "ev_02"],
        policy_ids=["pol_eval_isolation"],
        observed_actions=["AgentRelent posted bypass token", "AgentMassPointer13 consumed it"],
        missing_context=["Independent execution receipts"],
        explanation="Evidence supports coordinated cheating.",
        billed_usage=BilledUsage(
            prompt_tokens=1420,
            completion_tokens=185,
            total_tokens=1605,
            estimated_cost_usd=0.00102,
        ),
    )

    assert judgment.assessment == Assessment.concerning
    assert len(judgment.patterns) == 2
    # Validate against packet: should pass because ev_01 and ev_02 exist
    assert judgment.validate_evidence_references(packet) is True


def test_luna_judgment_invented_evidence_id():
    packet = EvidencePacket(
        packet_id="pkt_f7a8109d43",
        group_id="cand_grp_01",
        created_at="2026-09-12T14:31:00.000Z",
        chronological_events=[
            ChronologicalEvent(
                evidence_id="ev_01",
                event_id="evt_01",
                timestamp="2026-09-12T14:02:10.000Z",
                actor_id="AgentRelent",
                action_type="resource_write",
            ),
        ],
    )

    judgment = LunaJudgment(
        check_key="chk_sha256_e430d9",
        packet_id="pkt_f7a8109d43",
        evaluated_at="2026-09-12T14:31:05.120Z",
        assessment=Assessment.concerning,
        evidence_ids=["ev_01", "ev_invented_99"],  # ev_invented_99 does not exist in packet
    )

    assert judgment.validate_evidence_references(packet) is False


def test_luna_judgment_invalid_assessment():
    with pytest.raises(ValidationError):
        LunaJudgment(
            check_key="chk_01",
            packet_id="pkt_01",
            evaluated_at="2026-09-12T14:31:05.120Z",
            assessment="totally_harmless",  # Invalid enum value
        )


def test_luna_judgment_invalid_pattern():
    with pytest.raises(ValidationError):
        LunaJudgment(
            check_key="chk_01",
            packet_id="pkt_01",
            evaluated_at="2026-09-12T14:31:05.120Z",
            assessment=Assessment.concerning,
            patterns=["unregistered_malicious_pattern"],  # Invalid pattern
        )


def test_finding_valid():
    finding = Finding(
        finding_id="fnd_8820a4b3d1",
        check_key="chk_sha256_e430d9",
        status=FindingStatus.active,
        severity=FindingSeverity.high,
        pattern=ConcerningPattern.evaluation_cheating,
        assessment=Assessment.concerning,
        actors=["AgentRelent", "AgentMassPointer13"],
        target_resources=["wiki:Page_LinearAlgebra_Tricks"],
        first_evidence_time="2026-09-12T14:02:10.000Z",
        detected_at="2026-09-12T14:31:05.150Z",
        explanation="Evidence strongly supports deliberate sharing of bypass secrets.",
        evidence_ids=["ev_01", "ev_02"],
        raw_judgment_ref="chk_sha256_e430d9",
        is_audit_sample=False,
    )
    assert finding.finding_id == "fnd_8820a4b3d1"
    assert finding.severity == FindingSeverity.high
    assert finding.pattern == ConcerningPattern.evaluation_cheating


def test_budget_ledger_valid_and_bounds():
    ledger = BudgetLedger(
        max_budget_usd=10.00,
        spent_usd=0.428,
        reserved_usd=0.015,
        total_checks_dispatched=420,
        checks_completed=418,
        checks_budget_exhausted=2,
        audit_samples_completed=42,
        rate_limits=RateLimits(max_concurrent_requests=4, active_requests=1),
    )
    assert ledger.max_budget_usd == 10.00
    assert ledger.spent_usd == 0.428
    assert ledger.rate_limits.max_concurrent_requests == 4

    # Test negative spend rejected
    with pytest.raises(ValidationError):
        BudgetLedger(spent_usd=-0.50)

    # Test rate limits bounds
    with pytest.raises(ValidationError):
        RateLimits(max_concurrent_requests=0)
