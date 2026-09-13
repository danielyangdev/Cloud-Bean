"""Deterministic Replay Engine consuming accepted judgments without new LLM calls."""

from typing import Dict, List, Optional, Tuple

from cloud_bean.engine.storage import JudgmentFindingStore, compute_finding_id
from cloud_bean.evidence.selector import EvidenceSelector
from cloud_bean.judge.client import LunaJudgeClient
from cloud_bean.schemas.candidate import CandidateGroup
from cloud_bean.schemas.events import FleetEvent
from cloud_bean.schemas.evidence import ActorContext, EvidencePacket, PolicyStatement
from cloud_bean.schemas.finding import Finding, FindingSeverity, FindingStatus
from cloud_bean.schemas.judgment import Assessment, LunaJudgment
from cloud_bean.signals.detector import FleetSignalEngine


class ReplayEngine:
    """Executes deterministic offline replay over recorded event streams using the accepted judgment ledger."""

    def __init__(
        self,
        store: JudgmentFindingStore,
        signal_engine: Optional[FleetSignalEngine] = None,
        evidence_selector: Optional[EvidenceSelector] = None,
        judge_client: Optional[LunaJudgeClient] = None,
    ) -> None:
        self.store = store
        self.signal_engine = signal_engine or FleetSignalEngine()
        self.evidence_selector = evidence_selector or EvidenceSelector()
        self.judge_client = judge_client or LunaJudgeClient()
        self.llm_calls_made = 0

    def replay_window(
        self,
        events: List[FleetEvent],
        window_start: str,
        window_end: str,
        policies: Optional[List[PolicyStatement]] = None,
        actor_contexts: Optional[List[ActorContext]] = None,
        enable_audit: bool = True,
    ) -> Tuple[List[Finding], List[str]]:
        """Replay events using persisted judgments. Returns (reproduced_findings, missing_judgment_keys)."""
        candidates = self.signal_engine.process_events(
            events=events,
            window_start=window_start,
            window_end=window_end,
            enable_audit=enable_audit,
        )

        replayed_findings: List[Finding] = []
        missing_keys: List[str] = []

        for candidate in candidates:
            packet = self.evidence_selector.build_packet(
                candidate=candidate,
                events=events,
                policies=policies,
                actor_contexts=actor_contexts,
            )

            # Compute deterministic check_key
            check_key = self.judge_client.compute_check_key(packet)

            # Retrieve persisted accepted judgment from store (ZERO LLM calls)
            stored_judgment = self.store.get_accepted_judgment(check_key)

            if stored_judgment is None:
                # If judgment is not in ledger, mark as pending/missing
                missing_keys.append(check_key)
                continue

            # Reconstruct findings from stored judgment
            if stored_judgment.assessment == Assessment.concerning and stored_judgment.patterns:
                first_ev_time = (
                    packet.chronological_events[0].timestamp
                    if packet.chronological_events
                    else window_start
                )

                for pattern in stored_judgment.patterns:
                    finding_id = compute_finding_id(stored_judgment.check_key, pattern)
                    finding = Finding(
                        finding_id=finding_id,
                        check_key=stored_judgment.check_key,
                        status=FindingStatus.active,
                        severity=FindingSeverity.high,
                        pattern=pattern,
                        assessment=stored_judgment.assessment,
                        actors=stored_judgment.actors or candidate.actors,
                        target_resources=candidate.target_resources,
                        first_evidence_time=first_ev_time,
                        detected_at=stored_judgment.evaluated_at,
                        explanation=stored_judgment.explanation,
                        evidence_ids=stored_judgment.evidence_ids,
                        raw_judgment_ref=stored_judgment.check_key,
                        is_audit_sample=candidate.is_audit_sample,
                    )
                    replayed_findings.append(finding)

        return replayed_findings, missing_keys
