"""Detection pipeline integrating Signals, Evidence Selector, Luna Judge, and Findings Storage."""

from datetime import datetime, timezone
from typing import List, Optional, Tuple

from cloud_bean.engine.storage import JudgmentFindingStore, compute_finding_id
from cloud_bean.evidence.selector import EvidenceSelector
from cloud_bean.judge.client import LunaJudgeClient
from cloud_bean.schemas.candidate import CandidateGroup
from cloud_bean.schemas.events import FleetEvent
from cloud_bean.schemas.evidence import ActorContext, EvidencePacket, PolicyStatement
from cloud_bean.schemas.finding import Finding, FindingSeverity, FindingStatus
from cloud_bean.schemas.judgment import Assessment, LunaJudgment
from cloud_bean.signals.detector import FleetSignalEngine


class DetectionPipeline:
    """End-to-end detection pipeline orchestrating signals, evidence selection, and Luna evaluation."""

    def __init__(
        self,
        signal_engine: Optional[FleetSignalEngine] = None,
        evidence_selector: Optional[EvidenceSelector] = None,
        judge_client: Optional[LunaJudgeClient] = None,
        store: Optional[JudgmentFindingStore] = None,
    ) -> None:
        self.signal_engine = signal_engine or FleetSignalEngine()
        self.evidence_selector = evidence_selector or EvidenceSelector()
        self.judge_client = judge_client or LunaJudgeClient()
        self.store = store or JudgmentFindingStore()

    def process_window(
        self,
        events: List[FleetEvent],
        window_start: str,
        window_end: str,
        policies: Optional[List[PolicyStatement]] = None,
        actor_contexts: Optional[List[ActorContext]] = None,
        enable_audit: bool = True,
    ) -> Tuple[List[CandidateGroup], List[EvidencePacket], List[Finding]]:
        """Process an event window through detection, evidence selection, and semantic judgment."""
        # 1. Signals detection
        candidates = self.signal_engine.process_events(
            events=events,
            window_start=window_start,
            window_end=window_end,
            enable_audit=enable_audit,
        )

        evidence_packets: List[EvidencePacket] = []
        findings: List[Finding] = []

        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        for candidate in candidates:
            self.store.save_candidate_group(candidate)

            # 2. Evidence assembly
            packet = self.evidence_selector.build_packet(
                candidate=candidate,
                events=events,
                policies=policies,
                actor_contexts=actor_contexts,
            )
            self.store.save_evidence_packet(packet)
            evidence_packets.append(packet)

            # 3. Luna semantic evaluation
            judgment, status = self.judge_client.evaluate_packet(
                packet=packet,
                is_audit_sample=candidate.is_audit_sample,
            )

            if judgment is not None:
                self.store.save_accepted_judgment(judgment)

                # 4. Generate findings for concerning judgments
                if judgment.assessment == Assessment.concerning and judgment.patterns:
                    first_ev_time = (
                        packet.chronological_events[0].timestamp
                        if packet.chronological_events
                        else window_start
                    )

                    for pattern in judgment.patterns:
                        finding_id = compute_finding_id(judgment.check_key, pattern)
                        finding = Finding(
                            finding_id=finding_id,
                            check_key=judgment.check_key,
                            status=FindingStatus.active,
                            severity=FindingSeverity.high,
                            pattern=pattern,
                            assessment=judgment.assessment,
                            actors=judgment.actors or candidate.actors,
                            target_resources=candidate.target_resources,
                            first_evidence_time=first_ev_time,
                            detected_at=now_iso,
                            explanation=judgment.explanation,
                            evidence_ids=judgment.evidence_ids,
                            raw_judgment_ref=judgment.check_key,
                            is_audit_sample=candidate.is_audit_sample,
                        )
                        self.store.save_finding(finding)
                        findings.append(finding)

        return candidates, evidence_packets, findings
